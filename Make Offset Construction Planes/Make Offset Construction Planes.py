import adsk.core
import adsk.fusion
import traceback


# ============================================================
# SETTINGS
# ============================================================

REFERENCE_PLANE_NAME = "Plane70"

# Number of NEW planes to create.
# Reference plane is NOT included.
# Use an even number for equal planes on both sides.
NUM_PLANES = 10

# Distance between adjacent planes
SPACING_MM = 0.25


def run(context):
    ui = None

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # Require an even number so both sides are symmetric
        if NUM_PLANES < 2 or NUM_PLANES % 2 != 0:
            ui.messageBox(
                "NUM_PLANES must be an even number "
                "so there are equal planes on both sides."
            )
            return

        # Find reference plane
        reference_plane = root.constructionPlanes.itemByName(
            REFERENCE_PLANE_NAME
        )

        if not reference_plane:
            ui.messageBox(
                f'Could not find reference plane "{REFERENCE_PLANE_NAME}"'
            )
            return

        # Fusion's internal distance unit is cm
        spacing_cm = SPACING_MM / 10.0

        planes_per_side = NUM_PLANES // 2

        # Generate offsets in spatial order:
        #
        # azimuth_plane_1   = most negative
        # ...
        # SliceReference    = center
        # ...
        # azimuth_plane_20  = most positive

        offsets = list(range(-planes_per_side, 0)) + \
                  list(range(1, planes_per_side + 1))

        for i, position in enumerate(offsets, start=1):

            offset_cm = position * spacing_cm

            plane_input = root.constructionPlanes.createInput()

            plane_input.setByOffset(
                reference_plane,
                adsk.core.ValueInput.createByReal(offset_cm)
            )

            new_plane = root.constructionPlanes.add(
                plane_input
            )

            new_plane.name = f"azimuth_plane_{i}"

        ui.messageBox(
            f"Done!\n\n"
            f"Created {NUM_PLANES} new planes\n"
            f"{planes_per_side} on each side\n"
            f"Spacing: {SPACING_MM} mm\n"
            f"Reference plane unchanged: {REFERENCE_PLANE_NAME}"
        )

    except:
        if ui:
            ui.messageBox(
                "Failed:\n{}".format(
                    traceback.format_exc()
                )
            )