import adsk.core
import adsk.fusion
import traceback
import math


# ============================================================
# ONE TOOTH TEST — N = 18
#
# Creates ONLY ONE tooth.
# No torus.
# No circular pattern.
# No construction planes.
#
# Fusion internal units = cm.
# ============================================================


# ------------------------------------------------------------
# PARAMETERS
# ------------------------------------------------------------

N_TEETH = 18

# Radius of the circular path that the teeth will eventually
# follow.
CORE_RADIUS_MM = 50.0

# Radial distance of the valley from the core path.
VALLEY_RADIUS_MM = 8.0

# Radial distance of the peak from the core path.
PEAK_RADIUS_MM = 16.0

# Width of the tooth perpendicular to the ring plane.
TOOTH_WIDTH_MM = 8.0


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def mm(x):
    return x / 10.0


def pt(x, y, z):
    return adsk.core.Point3D.create(x, y, z)


def vec(x, y, z):
    return adsk.core.Vector3D.create(x, y, z)


# ============================================================
# MAKE A BOX BETWEEN TWO ANGLES
#
# We'll make the tooth from TWO tapered wedge halves:
#
#       peak
#        /\
#       /  \
#      /    \
# valley    valley
#
# Each half is approximated by a rotated box/wedge.
# ============================================================

def make_half_tooth(
    temp,
    angle_valley,
    angle_peak,
    core_radius,
    valley_radius,
    peak_radius,
    tooth_width
):

    # --------------------------------------------------------
    # Points along the CENTER of the ring.
    # --------------------------------------------------------

    cv = pt(
        core_radius * math.cos(angle_valley),
        core_radius * math.sin(angle_valley),
        0
    )

    cp = pt(
        core_radius * math.cos(angle_peak),
        core_radius * math.sin(angle_peak),
        0
    )


    # --------------------------------------------------------
    # Radial directions
    # --------------------------------------------------------

    rv = vec(
        math.cos(angle_valley),
        math.sin(angle_valley),
        0
    )

    rp = vec(
        math.cos(angle_peak),
        math.sin(angle_peak),
        0
    )


    # --------------------------------------------------------
    # Outer valley and peak points.
    #
    # These form the visible tooth tip/flank.
    # --------------------------------------------------------

    valley_outer = pt(
        cv.x + rv.x * valley_radius,
        cv.y + rv.y * valley_radius,
        0
    )

    peak_outer = pt(
        cp.x + rp.x * peak_radius,
        cp.y + rp.y * peak_radius,
        0
    )


    # --------------------------------------------------------
    # Inner points.
    #
    # For now these sit on the core path.
    # --------------------------------------------------------

    valley_inner = cv
    peak_inner = cp


    # ========================================================
    # Construct a wedge-shaped temporary solid by creating
    # a box and intersecting it with another rotated box.
    #
    # More importantly, everything here uses supported
    # TemporaryBRep primitives.
    # ========================================================


    # Direction from valley to peak.
    direction = vec(
        peak_outer.x - valley_outer.x,
        peak_outer.y - valley_outer.y,
        0
    )

    length = math.sqrt(
        direction.x ** 2 +
        direction.y ** 2
    )

    direction.normalize()


    # In-plane direction perpendicular to the flank.
    perpendicular = vec(
        -direction.y,
        direction.x,
        0
    )

    perpendicular.normalize()


    # Midpoint of outer flank.
    mid_outer = pt(
        (valley_outer.x + peak_outer.x) / 2.0,
        (valley_outer.y + peak_outer.y) / 2.0,
        0
    )


    # Estimate required radial depth.
    depth = peak_radius


    # Shift inward from outer flank.
    center = pt(
        mid_outer.x - perpendicular.x * depth / 2.0,
        mid_outer.y - perpendicular.y * depth / 2.0,
        0
    )


    z_axis = vec(
        0,
        0,
        1
    )


    # --------------------------------------------------------
    # Main solid.
    #
    # local length = along flank
    # local width  = Z
    # local height = inward toward ring center
    # --------------------------------------------------------

    box_def = adsk.core.OrientedBoundingBox3D.create(
        center,
        direction,
        z_axis,
        length,
        tooth_width,
        depth
    )


    body = temp.createBox(
        box_def
    )


    return body


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
                "Open a Fusion design first."
            )

            return


        # Direct mode works well with TemporaryBRep.
        design.designType = (
            adsk.fusion.DesignTypes.DirectDesignType
        )


        root = design.rootComponent

        temp = (
            adsk.fusion
            .TemporaryBRepManager
            .get()
        )


        # ====================================================
        # DIMENSIONS
        # ====================================================

        R = mm(
            CORE_RADIUS_MM
        )

        valley_r = mm(
            VALLEY_RADIUS_MM
        )

        peak_r = mm(
            PEAK_RADIUS_MM
        )

        width = mm(
            TOOTH_WIDTH_MM
        )


        # ====================================================
        # N = 18
        #
        # 360 / 18 = 20 degrees per tooth.
        #
        # Our single tooth goes:
        #
        # -10° ---- 0° ---- +10°
        #
        # ====================================================

        tooth_angle = (
            2.0 *
            math.pi /
            N_TEETH
        )

        half = (
            tooth_angle /
            2.0
        )


        # ====================================================
        # LEFT HALF
        #
        # valley at -10°
        # peak at 0°
        # ====================================================

        left = make_half_tooth(
            temp,
            -half,
            0.0,
            R,
            valley_r,
            peak_r,
            width
        )


        if not left:

            raise RuntimeError(
                "Failed to create left tooth half."
            )


        # ====================================================
        # RIGHT HALF
        #
        # peak at 0°
        # valley at +10°
        #
        # Reverse arguments.
        # ====================================================

        right = make_half_tooth(
            temp,
            half,
            0.0,
            R,
            valley_r,
            peak_r,
            width
        )


        if not right:

            raise RuntimeError(
                "Failed to create right tooth half."
            )


        # ====================================================
        # UNION THE TWO HALVES
        # ====================================================

        success = temp.booleanOperation(
            left,
            right,
            adsk.fusion.BooleanTypes.UnionBooleanType
        )


        if not success:

            # If Fusion doesn't like the union, show both
            # pieces separately so we can still inspect them.

            body_left = root.bRepBodies.add(
                left
            )

            body_left.name = (
                "TOOTH_LEFT_HALF"
            )


            body_right = root.bRepBodies.add(
                right
            )

            body_right.name = (
                "TOOTH_RIGHT_HALF"
            )


        else:

            body = root.bRepBodies.add(
                left
            )

            body.name = (
                "ONE_TOOTH_N18"
            )


        # ====================================================
        # VIEW
        # ====================================================

        app.activeViewport.fit()


        ui.messageBox(

            "Created ONE tooth test.\n\n"

            "N = %d\n"
            "One tooth = %.1f degrees\n"
            "Valley = %.1f mm\n"
            "Peak = %.1f mm\n"
            "Width = %.1f mm\n\n"

            "No ring or circular pattern was created."

            %

            (
                N_TEETH,
                math.degrees(tooth_angle),
                VALLEY_RADIUS_MM,
                PEAK_RADIUS_MM,
                TOOTH_WIDTH_MM
            )
        )


    except:

        if ui:

            ui.messageBox(
                "FAILED:\n\n"
                + traceback.format_exc()
            )