import adsk.core
import adsk.fusion
import math
import traceback


# ============================================================
# SETTINGS
# ============================================================

RIDGE_WIDTH_PARAM = 'ridgeWidth'
RIDGE_HEIGHT_PARAM = 'ridgeHeight'

DEFAULT_RIDGE_WIDTH = '5 mm'
DEFAULT_RIDGE_HEIGHT = '2 mm'

# Keep low while debugging.
NUM_SECTIONS = 8

# Number of points defining the cosine^2 ridge top.
PROFILE_POINTS = 11

# Leave these FALSE for now so we can inspect the geometry.
HIDE_PROFILE_SKETCHES = False
HIDE_CONSTRUCTION_PLANES = False


# ============================================================
# PARAMETERS
# ============================================================

def get_or_create_user_parameter(
    design,
    name,
    expression,
    units,
    comment
):
    params = design.userParameters

    param = params.itemByName(name)

    if param:
        return param

    return params.add(
        name,
        adsk.core.ValueInput.createByString(expression),
        units,
        comment
    )


# ============================================================
# SELECTION
# ============================================================

def get_selected_sphere_and_paths(ui):
    """
    Preselect:

        - exactly one spherical BRepFace
        - one or more projected SketchCurves
    """

    selections = ui.activeSelections

    sphere_face = None
    curves = []

    for i in range(selections.count):

        ent = selections.item(i).entity

        # ----------------------------------------------------
        # Spherical face
        # ----------------------------------------------------

        face = adsk.fusion.BRepFace.cast(ent)

        if face:

            sphere = adsk.core.Sphere.cast(
                face.geometry
            )

            if sphere:

                if sphere_face is not None:

                    raise RuntimeError(
                        'Select only ONE spherical face.'
                    )

                sphere_face = face
                continue

        # ----------------------------------------------------
        # Sketch curve
        # ----------------------------------------------------

        curve = adsk.fusion.SketchCurve.cast(ent)

        if curve:

            curves.append(curve)

    if sphere_face is None:

        raise RuntimeError(
            'No spherical face selected.\n\n'
            'Select the sphere face and the projected curves '
            'before running the script.'
        )

    if len(curves) == 0:

        raise RuntimeError(
            'No projected sketch curves selected.'
        )

    return sphere_face, curves


# ============================================================
# WORLD CURVE GEOMETRY
# ============================================================

def get_world_curve_geometry(sketch_curve):
    """
    Get model-space geometry for the selected SketchCurve.
    """

    try:

        return sketch_curve.worldGeometry

    except:

        return sketch_curve.geometry


# ============================================================
# ACTUAL POINT AT ARC-LENGTH FRACTION
# ============================================================

def evaluate_point_at_arc_fraction(
    sketch_curve,
    fraction
):
    """
    Return the actual model-space point located at a given
    FRACTION OF ARC LENGTH along the selected curve.

    Example:

        fraction = 0.0
            start

        fraction = 0.5
            halfway along physical curve length

        fraction = 1.0
            end

    This is intentionally NOT linear interpolation in the
    curve's parameter space.
    """

    geom = get_world_curve_geometry(
        sketch_curve
    )

    evaluator = geom.evaluator

    # --------------------------------------------------------
    # Get curve parameter range
    # --------------------------------------------------------

    result = evaluator.getParameterExtents()

    if not result[0]:

        raise RuntimeError(
            'Could not determine curve parameter extents.'
        )

    start_param = result[1]
    end_param = result[2]

    # --------------------------------------------------------
    # Determine total physical curve length
    # --------------------------------------------------------

    result = evaluator.getLengthAtParameter(
        start_param,
        end_param
    )

    if not result[0]:

        raise RuntimeError(
            'Could not determine physical curve length.'
        )

    total_length = result[1]

    if total_length <= 1e-9:

        raise RuntimeError(
            'Selected curve has effectively zero length.'
        )

    # --------------------------------------------------------
    # Desired physical distance from start
    # --------------------------------------------------------

    target_length = (
        total_length *
        fraction
    )

    # --------------------------------------------------------
    # Convert physical distance back to curve parameter
    # --------------------------------------------------------

    result = evaluator.getParameterAtLength(
        start_param,
        target_length
    )

    if not result[0]:

        raise RuntimeError(
            f'Could not find curve parameter at '
            f'fraction {fraction:.4f}.'
        )

    parameter = result[1]

    # --------------------------------------------------------
    # Evaluate actual 3D point
    # --------------------------------------------------------

    result = evaluator.getPointAtParameter(
        parameter
    )

    if not result[0]:

        raise RuntimeError(
            f'Could not evaluate point at '
            f'fraction {fraction:.4f}.'
        )

    return result[1]


# ============================================================
# PATH
# ============================================================

def make_path(sketch_curve):
    """
    Convert selected SketchCurve into Fusion Path.
    """

    path = adsk.fusion.Path.create(
        sketch_curve,
        adsk.fusion.ChainedCurveOptions.noChainedCurves
    )

    if not path:

        raise RuntimeError(
            'Could not create Fusion Path '
            'from selected sketch curve.'
        )

    return path


# ============================================================
# SECTION PLANE
# ============================================================

def make_section_plane(
    root,
    path,
    fraction,
    ridge_index,
    section_index
):
    """
    Create a plane perpendicular to the Fusion Path at
    the given proportional distance along it.
    """

    planes = root.constructionPlanes

    plane_input = planes.createInput()

    position = (
        adsk.core.ValueInput.createByReal(
            fraction
        )
    )

    success = plane_input.setByPath(
        path,
        adsk.fusion.PathDistanceTypes
        .ProportionalPathDistanceType,
        position
    )

    if not success:

        raise RuntimeError(
            f'setByPath failed at '
            f'fraction {fraction:.4f}.'
        )

    plane = planes.add(
        plane_input
    )

    if not plane:

        raise RuntimeError(
            'Fusion did not create '
            'the construction plane.'
        )

    plane.name = (
        f'Ridge {ridge_index:02d} '
        f'Plane {section_index:02d}'
    )

    if HIDE_CONSTRUCTION_PLANES:

        plane.isLightBulbOn = False

    return plane


# ============================================================
# SNAP POINT TO SPHERE
# ============================================================

def snap_point_to_sphere(
    point,
    sphere_center,
    sphere_radius
):
    """
    Radially project a point onto the exact sphere.
    """

    dx = (
        point.x -
        sphere_center.x
    )

    dy = (
        point.y -
        sphere_center.y
    )

    dz = (
        point.z -
        sphere_center.z
    )

    length = math.sqrt(
        dx * dx +
        dy * dy +
        dz * dz
    )

    if length < 1e-9:

        raise RuntimeError(
            'Cannot project sphere center '
            'onto sphere.'
        )

    dx /= length
    dy /= length
    dz /= length

    return adsk.core.Point3D.create(

        sphere_center.x +
        sphere_radius * dx,

        sphere_center.y +
        sphere_radius * dy,

        sphere_center.z +
        sphere_radius * dz
    )


# ============================================================
# RIDGE PROFILE
# ============================================================

def make_ridge_profile(
    root,
    plane,
    sphere_center,
    path_point,
    sphere_radius,
    ridge_width,
    ridge_height,
    ridge_index,
    section_index
):
    """
    Create one ridge cross-section.

                         ridge
                           /\\
                        __/  \\__
                     .-'        '-.
                   .'              '.
                          sphere

    Bottom:
        exact sphere arc

    Top:
        cosine^2 bump
    """

    # --------------------------------------------------------
    # Create sketch on section plane
    # --------------------------------------------------------

    sketch = root.sketches.add(
        plane
    )

    if not sketch:

        raise RuntimeError(
            'Could not create profile sketch.'
        )

    sketch.name = (
        f'Ridge {ridge_index:02d} '
        f'Section {section_index:02d}'
    )

    # --------------------------------------------------------
    # Convert sphere center and ACTUAL path point into
    # this sketch's coordinate system.
    # --------------------------------------------------------

    center_2d = (
        sketch.modelToSketchSpace(
            sphere_center
        )
    )

    point_2d = (
        sketch.modelToSketchSpace(
            path_point
        )
    )

    # --------------------------------------------------------
    # Radial direction in sketch
    # --------------------------------------------------------

    ux = (
        point_2d.x -
        center_2d.x
    )

    uy = (
        point_2d.y -
        center_2d.y
    )

    radial_length = math.sqrt(
        ux * ux +
        uy * uy
    )

    if radial_length < 1e-9:

        raise RuntimeError(
            'Sphere center and path point '
            'collapsed in sketch space.'
        )

    ux /= radial_length
    uy /= radial_length

    # Sideways direction.
    vx = -uy
    vy = ux

    # --------------------------------------------------------
    # Surface ridge width -> angular half width
    # --------------------------------------------------------

    half_width = (
        ridge_width /
        2.0
    )

    alpha = (
        half_width /
        sphere_radius
    )

    if alpha <= 0:

        raise RuntimeError(
            'ridgeWidth must be positive.'
        )

    if alpha >= math.pi / 2:

        raise RuntimeError(
            'ridgeWidth is too large '
            'relative to sphere radius.'
        )

    # --------------------------------------------------------
    # Point at radius + angular offset in this section plane
    # --------------------------------------------------------

    def polar_point(
        theta,
        radius
    ):

        dx = (
            math.cos(theta) * ux +
            math.sin(theta) * vx
        )

        dy = (
            math.cos(theta) * uy +
            math.sin(theta) * vy
        )

        return adsk.core.Point3D.create(

            center_2d.x +
            radius * dx,

            center_2d.y +
            radius * dy,

            0
        )

    # --------------------------------------------------------
    # Contact points with sphere
    # --------------------------------------------------------

    left = polar_point(
        -alpha,
        sphere_radius
    )

    middle = polar_point(
        0.0,
        sphere_radius
    )

    right = polar_point(
        alpha,
        sphere_radius
    )

    # --------------------------------------------------------
    # Exact sphere arc forming bottom
    # --------------------------------------------------------

    bottom_arc = (
        sketch.sketchCurves
        .sketchArcs
        .addByThreePoints(
            right,
            middle,
            left
        )
    )

    if not bottom_arc:

        raise RuntimeError(
            'Could not create spherical '
            'bottom arc.'
        )

    # --------------------------------------------------------
    # Cosine^2 upper ridge
    # --------------------------------------------------------

    top_points = (
        adsk.core.ObjectCollection.create()
    )

    for j in range(PROFILE_POINTS):

        fraction = (
            j /
            (PROFILE_POINTS - 1)
        )

        theta = (
            -alpha +
            2.0 *
            alpha *
            fraction
        )

        phase = (
            math.pi *
            theta /
            (2.0 * alpha)
        )

        bump = (
            ridge_height *
            (
                math.cos(phase) ** 2
            )
        )

        radius = (
            sphere_radius +
            bump
        )

        # Exact shared endpoints.
        if j == 0:

            point = left

        elif j == PROFILE_POINTS - 1:

            point = right

        else:

            point = polar_point(
                theta,
                radius
            )

        top_points.add(
            point
        )

    # --------------------------------------------------------
    # Smooth spline through top points
    # --------------------------------------------------------

    top_spline = (
        sketch.sketchCurves
        .sketchFittedSplines
        .add(
            top_points
        )
    )

    if not top_spline:

        raise RuntimeError(
            'Could not create ridge '
            'top spline.'
        )

    # --------------------------------------------------------
    # Closed profile check
    # --------------------------------------------------------

    if sketch.profiles.count == 0:

        raise RuntimeError(
            'Ridge cross-section did not '
            'form a closed profile.'
        )

    profile = (
        sketch.profiles.item(0)
    )

    # --------------------------------------------------------
    # If Fusion finds multiple regions,
    # use smallest region.
    # --------------------------------------------------------

    if sketch.profiles.count > 1:

        smallest = None
        smallest_area = None

        for i in range(
            sketch.profiles.count
        ):

            candidate = (
                sketch.profiles.item(i)
            )

            props = (
                candidate.areaProperties(
                    adsk.fusion
                    .CalculationAccuracy
                    .MediumCalculationAccuracy
                )
            )

            area = props.area

            if (
                smallest is None or
                area < smallest_area
            ):

                smallest = candidate
                smallest_area = area

        profile = smallest

    return (
        sketch,
        profile
    )


# ============================================================
# LOFT
# ============================================================

def create_ridge_loft(
    root,
    profiles,
    ridge_index
):
    """
    Loft through all generated ridge profiles.
    """

    if len(profiles) < 2:

        raise RuntimeError(
            'At least two profiles '
            'are required for a loft.'
        )

    lofts = (
        root.features.loftFeatures
    )

    loft_input = (
        lofts.createInput(
            adsk.fusion.FeatureOperations
            .NewBodyFeatureOperation
        )
    )

    if not loft_input:

        raise RuntimeError(
            'Could not create LoftFeatureInput.'
        )

    loft_input.isSolid = True

    # --------------------------------------------------------
    # Add sections IN ORDER
    # --------------------------------------------------------

    for i, profile in enumerate(
        profiles,
        start=1
    ):

        try:

            loft_input.loftSections.add(
                profile
            )

        except Exception as e:

            raise RuntimeError(
                f'Could not add loft '
                f'section {i}: {e}'
            )

    # --------------------------------------------------------
    # Create loft
    # --------------------------------------------------------

    try:

        loft = lofts.add(
            loft_input
        )

    except Exception as e:

        raise RuntimeError(
            f'Fusion loft solver failed: {e}'
        )

    if not loft:

        raise RuntimeError(
            'Fusion returned no loft feature.'
        )

    loft.name = (
        f'Ridge Loft {ridge_index:02d}'
    )

    for i in range(
        loft.bodies.count
    ):

        loft.bodies.item(i).name = (
            f'Ridge Body {ridge_index:02d}'
        )

    return loft


# ============================================================
# CREATE ONE RIDGE
# ============================================================

def create_one_ridge(
    root,
    sketch_curve,
    sphere_center,
    sphere_radius,
    ridge_width,
    ridge_height,
    ridge_index
):
    """
    Generate one ridge.

    The SAME fraction is used for:

        setByPath()
        evaluate_point_at_arc_fraction()

    so the plane and actual curve point correspond to the
    same physical position along the curve.
    """

    # --------------------------------------------------------
    # Fusion Path
    # --------------------------------------------------------

    try:

        path = make_path(
            sketch_curve
        )

    except Exception as e:

        raise RuntimeError(
            f'PATH creation failed: {e}'
        )

    profiles = []
    sketches = []
    planes = []

    # --------------------------------------------------------
    # Generate sections
    # --------------------------------------------------------

    for i in range(
        NUM_SECTIONS
    ):

        section_num = (
            i + 1
        )

        fraction = (
            i /
            (NUM_SECTIONS - 1)
        )

        # ----------------------------------------------------
        # STEP 1:
        # Fusion creates a perpendicular plane at this
        # proportional position along the path.
        # ----------------------------------------------------

        try:

            plane = make_section_plane(
                root,
                path,
                fraction,
                ridge_index,
                section_num
            )

        except Exception as e:

            raise RuntimeError(
                f'SECTION {section_num}: '
                f'plane creation failed: {e}'
            )

        # ----------------------------------------------------
        # STEP 2:
        # Evaluate ACTUAL curve point at same ARC-LENGTH
        # fraction.
        # ----------------------------------------------------

        try:

            path_point = (
                evaluate_point_at_arc_fraction(
                    sketch_curve,
                    fraction
                )
            )

        except Exception as e:

            raise RuntimeError(
                f'SECTION {section_num}: '
                f'path point evaluation failed: {e}'
            )

        # ----------------------------------------------------
        # STEP 3:
        # Snap actual curve point onto exact sphere.
        #
        # Because your path was projected onto the sphere,
        # this should only make a tiny numerical correction.
        # ----------------------------------------------------

        try:

            sphere_point = (
                snap_point_to_sphere(
                    path_point,
                    sphere_center,
                    sphere_radius
                )
            )

        except Exception as e:

            raise RuntimeError(
                f'SECTION {section_num}: '
                f'sphere projection failed: {e}'
            )

        # ----------------------------------------------------
        # STEP 4:
        # Create cross-section centered on that sphere point.
        # ----------------------------------------------------

        try:

            sketch, profile = (
                make_ridge_profile(
                    root,
                    plane,
                    sphere_center,
                    sphere_point,
                    sphere_radius,
                    ridge_width,
                    ridge_height,
                    ridge_index,
                    section_num
                )
            )

        except Exception as e:

            raise RuntimeError(
                f'SECTION {section_num}: '
                f'profile creation failed: {e}'
            )

        planes.append(
            plane
        )

        sketches.append(
            sketch
        )

        profiles.append(
            profile
        )

    # --------------------------------------------------------
    # STEP 5:
    # Loft through profiles.
    # --------------------------------------------------------

    try:

        loft = create_ridge_loft(
            root,
            profiles,
            ridge_index
        )

    except Exception as e:

        raise RuntimeError(
            f'LOFT creation failed: {e}'
        )

    # --------------------------------------------------------
    # Visibility
    # --------------------------------------------------------

    if HIDE_PROFILE_SKETCHES:

        for sketch in sketches:

            sketch.isLightBulbOn = False

    if HIDE_CONSTRUCTION_PLANES:

        for plane in planes:

            plane.isLightBulbOn = False

    return loft


# ============================================================
# MAIN
# ============================================================

def run(context):

    ui = None

    try:

        app = (
            adsk.core.Application.get()
        )

        ui = (
            app.userInterface
        )

        design = (
            adsk.fusion.Design.cast(
                app.activeProduct
            )
        )

        if not design:

            ui.messageBox(
                'Open a Fusion design '
                'before running this script.'
            )

            return

        root = (
            design.rootComponent
        )

        # ----------------------------------------------------
        # Read selection
        # ----------------------------------------------------

        sphere_face, curves = (
            get_selected_sphere_and_paths(
                ui
            )
        )

        # ----------------------------------------------------
        # Sphere geometry
        # ----------------------------------------------------

        sphere = (
            adsk.core.Sphere.cast(
                sphere_face.geometry
            )
        )

        if not sphere:

            raise RuntimeError(
                'Selected face is not '
                'an analytic spherical face.'
            )

        sphere_center = (
            sphere.origin
        )

        sphere_radius = (
            sphere.radius
        )

        # ----------------------------------------------------
        # User parameters
        # ----------------------------------------------------

        width_param = (
            get_or_create_user_parameter(
                design,
                RIDGE_WIDTH_PARAM,
                DEFAULT_RIDGE_WIDTH,
                'mm',
                'Surface width of generated ridges'
            )
        )

        height_param = (
            get_or_create_user_parameter(
                design,
                RIDGE_HEIGHT_PARAM,
                DEFAULT_RIDGE_HEIGHT,
                'mm',
                'Maximum height of generated ridges'
            )
        )

        # Fusion API internal length units are centimeters.
        ridge_width = (
            width_param.value
        )

        ridge_height = (
            height_param.value
        )

        if ridge_width <= 0:

            raise RuntimeError(
                'ridgeWidth must be greater than zero.'
            )

        if ridge_height <= 0:

            raise RuntimeError(
                'ridgeHeight must be greater than zero.'
            )

        # ----------------------------------------------------
        # Generate ridges
        # ----------------------------------------------------

        succeeded = 0
        failures = []

        for ridge_index, curve in enumerate(
            curves,
            start=1
        ):

            try:

                create_one_ridge(
                    root,
                    curve,
                    sphere_center,
                    sphere_radius,
                    ridge_width,
                    ridge_height,
                    ridge_index
                )

                succeeded += 1

            except Exception as e:

                failures.append(
                    f'{ridge_index}: {e}'
                )

        # ----------------------------------------------------
        # Report
        # ----------------------------------------------------

        msg = (
            'Radial ridge generation complete.\n\n'
            f'Succeeded: {succeeded}\n'
            f'Failed: {len(failures)}\n\n'
            f'ridgeWidth = '
            f'{width_param.expression}\n'
            f'ridgeHeight = '
            f'{height_param.expression}\n'
            f'Cross-sections per ridge = '
            f'{NUM_SECTIONS}'
        )

        if failures:

            msg += (
                '\n\nFailed ridge(s):\n'
                +
                '\n'.join(
                    failures[:10]
                )
            )

        ui.messageBox(
            msg
        )

    except:

        if ui:

            ui.messageBox(
                'Radial ridge script failed:\n\n'
                +
                traceback.format_exc()
            )