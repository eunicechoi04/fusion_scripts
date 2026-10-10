import adsk.core
import adsk.fusion
import traceback


# ============================================================
# SETTINGS
# ============================================================

FIRST_MESH = 2
LAST_MESH = 13

# THICKNESS_PARAMETER = "cardboard_thickness"
THICKNESS_PARAMETER = "temp_thickness"


def run(context):
    ui = None

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # ----------------------------------------------------
        # Check thickness parameter
        # ----------------------------------------------------

        thickness_param = design.userParameters.itemByName(
            THICKNESS_PARAMETER
        )

        if not thickness_param:
            ui.messageBox(
                f'Could not find parameter "{THICKNESS_PARAMETER}".'
            )
            return

        extrudes = root.features.extrudeFeatures

        # ----------------------------------------------------
        # Go through mesh sketches
        # ----------------------------------------------------

        for n in range(FIRST_MESH, LAST_MESH + 1):

            sketch_name = f"mesh {n}"
            # sketch_name = f"mesh azimuth_plane_{n}"

            sketch = root.sketches.itemByName(sketch_name)

            if not sketch:
                ui.messageBox(
                    f'Could not find "{sketch_name}". Skipping.'
                )
                continue

            num_profiles = sketch.profiles.count

            if num_profiles == 0:
                ui.messageBox(
                    f'"{sketch_name}" has no closed profiles. Skipping.'
                )
                continue

            # ------------------------------------------------
            # Extrude each closed profile independently
            # ------------------------------------------------

            for profile_index in range(num_profiles):

                profile = sketch.profiles.item(profile_index)

                # Naming starts at 1, not 0
                piece_number = profile_index + 1

                piece_name = (
                    f"{sketch.name} - body  {piece_number}"
                )

                # --------------------------------------------
                # Extrude this one profile
                # --------------------------------------------

                extrude_input = extrudes.createInput(
                    profile,
                    adsk.fusion.FeatureOperations.NewBodyFeatureOperation
                )

                half_thickness = adsk.core.ValueInput.createByString(
                    f"{THICKNESS_PARAMETER} / 2"
                )
                extrude_input.setSymmetricExtent(
                    half_thickness,
                    False
                )

                extrude = extrudes.add(extrude_input)

                extrude.name = f"Extrude {piece_name}"

                # There should be exactly one body because
                # we're extruding one profile.
                body = extrude.bodies.item(0)

                # --------------------------------------------
                # Create a component for this physical piece
                # --------------------------------------------

                occurrence = root.occurrences.addNewComponent(
                    adsk.core.Matrix3D.create()
                )

                component = occurrence.component
                component.name = piece_name

                # --------------------------------------------
                # Move body into component
                # --------------------------------------------

                moved_body = body.moveToComponent(
                    occurrence
                )

                moved_body.name = piece_name

            # Hide source sketch after all profiles are done
            sketch.isLightBulbOn = False

        ui.messageBox("Done!")

    except:
        if ui:
            ui.messageBox(
                "Failed:\n{}".format(
                    traceback.format_exc()
                )
            )