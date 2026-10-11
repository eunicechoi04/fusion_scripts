import adsk.core
import adsk.fusion
import math
import traceback


# ============================================================
# SETTINGS
# ============================================================

RIDGE_WIDTH_PARAM = 'ridgeWidth'
RIDGE_HEIGHT_PARAM = 'ridgeHeight'

DEFAULT_RIDGE_WIDTH = '8 mm'
DEFAULT_RIDGE_HEIGHT = '2 mm'

# Number of points used for the smooth upper ridge spline.
# 9-13 is usually plenty.
TOP_SPLINE_POINTS = 11

# Leave False while testing.
# True attempts to create the sweep directly as a Join operation.
JOIN_DIRECTLY = False

# Hide generated profile sketches after creation.
HIDE_PROFILE_SKETCHES = True

# Hide generated construction planes.
HIDE_CONSTRUCTION_PLANES = True


# ============================================================
# HELPERS
# ============================================================

def get_or_create_user_parameter(design, name, expression, units, comment):
    params = design.userParameters
    p = params.itemByName(name)

    if p:
        return p

    return params.add(
        name,
        adsk.core.ValueInput.createByString(expression),
        units,
        comment
    )


def get_selected_sphere_and_paths(ui):
    """
    Expected selection BEFORE running script:
        - one or more spherical BRepFaces from the same sphere
        - one or more SketchCurves (your projected paths)
    """

    sels = ui.activeSelections

    sphere_faces = []
    paths = []

    for i in range(sels.count):
        ent = sels.item(i).entity

        # Collect spherical faces
        face = adsk.fusion.BRepFace.cast(ent)

        if face:
            sphere = adsk.core.Sphere.cast(face.geometry)

            if sphere:
                sphere_faces.append(face)
                continue

        # Collect projected sketch curves
        sketch_curve = adsk.fusion.SketchCurve.cast(ent)

        if sketch_curve:
            paths.append(sketch_curve)

    if len(sphere_faces) == 0:
        raise RuntimeError(
            'No spherical face selected.\n\n'
            'Preselect one or more spherical faces plus all '
            'projected curves, then run the script.'
        )

    if len(paths) == 0:
        raise RuntimeError(
            'No sketch curves selected.\n\n'
            'Preselect the projected curves you want to turn into ridges.'
        )

    # All selected faces should be pieces of the SAME sphere.
    reference_sphere = adsk.core.Sphere.cast(
        sphere_faces[0].geometry
    )

    reference_center = reference_sphere.origin
    reference_radius = reference_sphere.radius

    tolerance = 1e-6

    for face in sphere_faces[1:]:

        sphere = adsk.core.Sphere.cast(
            face.geometry
        )

        center = sphere.origin

        same_center = (
            abs(center.x - reference_center.x) <= tolerance
            and abs(center.y - reference_center.y) <= tolerance
            and abs(center.z - reference_center.z) <= tolerance
        )

        same_radius = (
            abs(sphere.radius - reference_radius)
            <= tolerance
        )

        if not (same_center and same_radius):
            raise RuntimeError(
                'All selected spherical faces must '
                'belong to the same sphere.'
            )

    # The rest of your script only needs one face to get
    # the sphere's center/radius, so return the first one.
    return sphere_faces[0], paths

def point2(x, y):
    return adsk.core.Point3D.create(x, y, 0)


def normalize2(x, y):
    length = math.sqrt(x * x + y * y)

    if length < 1e-9:
        raise RuntimeError('Zero-length 2D vector.')

    return x / length, y / length


def get_curve_start_point(curve):
    """
    Get a model-space endpoint from a selected sketch curve.
    """

    geom = curve.geometry
    evaluator = geom.evaluator

    result = evaluator.getEndPoints()

    if not result[0]:
        raise RuntimeError('Could not get path endpoints.')

    return result[1]


def make_profile(
    root,
    design,
    path,
    sphere_center,
    sphere_radius,
    ridge_width,
    ridge_height,
    index
):
    """
    Creates a sketch normal to the path start.

    Cross section:
        top = smooth cosine^2 raised spline
        bottom = exact sphere circle arc

    Returns:
        sketch, profile, construction plane
    """

    # --------------------------------------------------------
    # Plane normal to path at its beginning
    # --------------------------------------------------------

    planes = root.constructionPlanes
    plane_input = planes.createInput()

    zero = adsk.core.ValueInput.createByReal(0.0)

    success = plane_input.setByPath(
        path,
        adsk.fusion.PathDistanceTypes.ProportionalPathDistanceType,
        zero
    )

    if not success:
        raise RuntimeError(
            f'Could not create path-normal plane for ridge {index}.'
        )

    plane = planes.add(plane_input)
    plane.name = f'Ridge Plane {index:02d}'

    if HIDE_CONSTRUCTION_PLANES:
        plane.isLightBulbOn = False

    # --------------------------------------------------------
    # Create profile sketch
    # --------------------------------------------------------

    sketch = root.sketches.add(plane)
    sketch.name = f'Ridge Profile {index:02d}'

    # Model-space starting point of sweep path.
    path_start_model = get_path_start_point(path)

    # Convert sphere center + path start into sketch coordinates.
    c = sketch.modelToSketchSpace(sphere_center)
    p = sketch.modelToSketchSpace(path_start_model)

    # Vector center -> path point in the profile plane.
    ux = p.x - c.x
    uy = p.y - c.y

    ux, uy = normalize2(ux, uy)

    # Perpendicular direction in profile plane.
    vx = -uy
    vy = ux

    # --------------------------------------------------------
    # Convert ridge width into angular half-width.
    #
    # ridgeWidth is interpreted as SURFACE ARC LENGTH.
    #
    #   total arc width = ridgeWidth
    #   alpha = half angle
    # --------------------------------------------------------

    half_width = ridge_width / 2.0
    alpha = half_width / sphere_radius

    # Prevent nonsensical giant profile.
    if alpha >= math.pi / 2:
        raise RuntimeError(
            'ridgeWidth is too large relative to sphere radius.'
        )

    # Utility: polar point around sphere center in this plane.
    def polar_point(theta, radius):
        direction_x = (
            math.cos(theta) * ux +
            math.sin(theta) * vx
        )

        direction_y = (
            math.cos(theta) * uy +
            math.sin(theta) * vy
        )

        return point2(
            c.x + radius * direction_x,
            c.y + radius * direction_y
        )

    # Contact points on sphere.
    left = polar_point(-alpha, sphere_radius)
    middle = polar_point(0.0, sphere_radius)
    right = polar_point(alpha, sphere_radius)

    # --------------------------------------------------------
    # Bottom = exact sphere arc
    # --------------------------------------------------------

    bottom_arc = sketch.sketchCurves.sketchArcs.addByThreePoints(
        right,
        middle,
        left
    )

    if not bottom_arc:
        raise RuntimeError(
            f'Could not create sphere arc for ridge {index}.'
        )

    # --------------------------------------------------------
    # Top = smooth bump
    #
    # h(theta) = H cos²(pi theta / 2 alpha)
    #
    # At theta = +/- alpha:
    #
    #   h = 0
    #   dh/dtheta = 0
    #
    # So the raised profile approaches the sphere tangentially.
    # --------------------------------------------------------

    # --------------------------------------------------------
    # Top = smooth bump
    # --------------------------------------------------------

    top_points = adsk.core.ObjectCollection.create()

    n = TOP_SPLINE_POINTS

    for j in range(n):
        t = j / (n - 1)

        theta = -alpha + 2.0 * alpha * t

        phase = (
            math.pi * theta /
            (2.0 * alpha)
        )

        bump = ridge_height * (math.cos(phase) ** 2)

        r = sphere_radius + bump

        # Force exact shared endpoints with sphere arc.
        if j == 0:
            pt = left
        elif j == n - 1:
            pt = right
        else:
            pt = polar_point(theta, r)

        top_points.add(pt)

    top_spline = (
        sketch.sketchCurves
        .sketchFittedSplines
        .add(top_points)
    )

    if not top_spline:
        raise RuntimeError(
            f'Could not create top spline for ridge {index}.'
        )

    # --------------------------------------------------------
    # Find resulting closed profile
    # --------------------------------------------------------

    if sketch.profiles.count == 0:
        raise RuntimeError(
            f'No closed profile was created for ridge {index}.'
        )

    # Usually exactly one profile.
    # If Fusion somehow generates more, choose the smallest area.
    profile = sketch.profiles.item(0)

    if sketch.profiles.count > 1:
        smallest = None
        smallest_area = None

        for i in range(sketch.profiles.count):
            test_profile = sketch.profiles.item(i)

            props = test_profile.areaProperties(
                adsk.fusion.CalculationAccuracy.MediumCalculationAccuracy
            )

            area = props.area

            if smallest is None or area < smallest_area:
                smallest = test_profile
                smallest_area = area

        profile = smallest

    if HIDE_PROFILE_SKETCHES:
        sketch.isLightBulbOn = False

    return sketch, profile, plane


def get_path_start_point(path):
    """
    Gets the first endpoint of the first path entity.
    """

    if path.count == 0:
        raise RuntimeError('Path contains no entities.')

    path_entity = path.item(0)

    curve = path_entity.entity

    # A PathEntity.entity can be a SketchCurve or BRepEdge.
    sketch_curve = adsk.fusion.SketchCurve.cast(curve)

    if sketch_curve:
        evaluator = sketch_curve.geometry.evaluator

    else:
        edge = adsk.fusion.BRepEdge.cast(curve)

        if not edge:
            raise RuntimeError('Unsupported sweep path entity.')

        evaluator = edge.evaluator

    result = evaluator.getEndPoints()

    if not result[0]:
        raise RuntimeError('Could not evaluate sweep path start.')

    return result[1]


def create_ridge_sweep(
    root,
    profile,
    path,
    sphere_face,
    index
):
    sweeps = root.features.sweepFeatures

    operation = (
        adsk.fusion.FeatureOperations
        .NewBodyFeatureOperation
    )

    sweep_input = sweeps.createInput(
        profile,
        path,
        operation
    )

    if not sweep_input:
        raise RuntimeError(
            f'Could not create sweep input for ridge {index}.'
        )

    # Keep profile normal to the path.
    sweep_input.orientation = (
        adsk.fusion.SweepOrientationTypes
        .PerpendicularOrientationType
    )

    sweep = sweeps.add(sweep_input)

    if not sweep:
        raise RuntimeError(
            f'Sweep failed for ridge {index}.'
        )

    sweep.name = f'Ridge {index:02d}'

    for i in range(sweep.bodies.count):
        sweep.bodies.item(i).name = (
            f'Ridge Body {index:02d}'
        )

    return sweep

# ============================================================
# MAIN
# ============================================================

def run(context):
    ui = None

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        design = adsk.fusion.Design.cast(
            app.activeProduct
        )

        if not design:
            ui.messageBox(
                'Open a Fusion design before running this script.'
            )
            return

        root = design.rootComponent

        # ----------------------------------------------------
        # Read selection
        # ----------------------------------------------------

        sphere_face, curves = (
            get_selected_sphere_and_paths(ui)
        )

        # ----------------------------------------------------
        # Verify selected face really is analytic sphere
        # ----------------------------------------------------

        sphere_geom = adsk.core.Sphere.cast(
            sphere_face.geometry
        )

        if not sphere_geom:
            raise RuntimeError(
                'Selected face is not an analytic spherical face.'
            )

        sphere_center = sphere_geom.origin
        sphere_radius = sphere_geom.radius

        # ----------------------------------------------------
        # User parameters
        # ----------------------------------------------------

        width_param = get_or_create_user_parameter(
            design,
            RIDGE_WIDTH_PARAM,
            DEFAULT_RIDGE_WIDTH,
            'mm',
            'Surface width of generated ridges'
        )

        height_param = get_or_create_user_parameter(
            design,
            RIDGE_HEIGHT_PARAM,
            DEFAULT_RIDGE_HEIGHT,
            'mm',
            'Maximum height of generated ridges'
        )

        # Fusion API length values are returned in internal units,
        # which are centimeters.
        ridge_width = width_param.value
        ridge_height = height_param.value

        if ridge_width <= 0:
            raise RuntimeError(
                'ridgeWidth must be greater than zero.'
            )

        if ridge_height <= 0:
            raise RuntimeError(
                'ridgeHeight must be greater than zero.'
            )

        # ----------------------------------------------------
        # Generate each ridge
        # ----------------------------------------------------

        succeeded = 0
        failed = []

        WIDTH_RETRY_FACTORS = [
            1.0,
            0.75,
            0.5,
            0.35,
            0.25,
        ]
        for index, curve in enumerate(curves, start=1):

            path = adsk.fusion.Path.create(
                curve,
                adsk.fusion.ChainedCurveOptions.noChainedCurves
            )

            if not path:
                failed.append(f'{index}: Could not create Path object.')
                continue

            ridge_created = False
            last_error = None

            for width_factor in WIDTH_RETRY_FACTORS:

                try:
                    test_width = ridge_width * width_factor

                    sketch, profile, plane = make_profile(
                        root,
                        design,
                        path,
                        sphere_center,
                        sphere_radius,
                        test_width,
                        ridge_height,
                        index
                    )

                    create_ridge_sweep(
                        root,
                        profile,
                        path,
                        sphere_face,
                        index
                    )

                    succeeded += 1
                    ridge_created = True

                    if width_factor < 1.0:
                        print(
                            f'Ridge {index} required width factor '
                            f'{width_factor:.2f}'
                        )

                    break

                except Exception as e:
                    last_error = str(e)

            if not ridge_created:
                failed.append(
                    f'{index}: {last_error}'
                )
        # ----------------------------------------------------
        # Report
        # ----------------------------------------------------

        msg = (
            f'Ridge generation complete.\n\n'
            f'Succeeded: {succeeded}\n'
            f'Failed: {len(failed)}\n\n'
            f'ridgeWidth = '
            f'{width_param.expression}\n'
            f'ridgeHeight = '
            f'{height_param.expression}'
        )

        if failed:
            msg += (
                '\n\nFailed ridge(s):\n' +
                '\n'.join(failed[:10])
            )

            if len(failed) > 10:
                msg += '\n...'

        ui.messageBox(msg)

    except:
        if ui:
            ui.messageBox(
                'Ridge script failed:\n\n'
                + traceback.format_exc()
            )