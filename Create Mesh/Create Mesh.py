"""This file acts as the main module for this script."""

# import traceback
# import adsk.core
# import adsk.fusion
# # import adsk.cam
# # import adsk.drawing

# # Initialize the global variables for the Application and UserInterface objects.
# app = adsk.core.Application.get()
# ui  = app.userInterface


# # def run(_context: str):
# #     """This function is called by Fusion when the script is run."""

# #     try:
# #         # Your code goes here.
# #         ui.messageBox(f'"{app.activeDocument.name}" is the active Document.')
# #     except:  #pylint:disable=bare-except
# #         # Write the error message to the TEXT COMMANDS window.
# #         app.log(f'Failed:\n{traceback.format_exc()}')

import adsk.core
import adsk.fusion
import traceback


MESH_NAME = "monkeyTrefoil"

# Example: Plane2 through Plane25
PLANE_NAMES = [f"azimuth_plane_{i}" for i in range(1, 11)]


def run(context):
    ui = None

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # Find mesh
        # Find mesh
        mesh = None

        for i in range(root.meshBodies.count):
            candidate = root.meshBodies.item(i)

            if candidate.name == MESH_NAME:
                mesh = candidate
                break

        if not mesh:
            ui.messageBox(f'Could not find mesh "{MESH_NAME}"')
            return

        # Create section sketch for each plane
        for plane_name in PLANE_NAMES:
            plane = root.constructionPlanes.itemByName(plane_name)

            if not plane:
                ui.messageBox(f'Could not find "{plane_name}"')
                continue

            old_count = root.sketches.count

            create_mesh_section(mesh, plane)

            adsk.doEvents()

            # Rename the sketch Fusion just created
            if root.sketches.count > old_count:
                sketch = root.sketches.item(root.sketches.count - 1)

                number = plane_name.replace("Plane", "")
                sketch.name = f"mesh {number}"

        ui.messageBox("Done!")

    except:
        if ui:
            ui.messageBox(
                "Failed:\n{}".format(traceback.format_exc())
            )


def create_mesh_section(mesh, plane):
    app = adsk.core.Application.get()
    ui = app.userInterface

    selections = ui.activeSelections
    selections.clear()

    # Start Mesh Section Sketch command
    app.executeTextCommand(
        "Commands.Start ParaMeshPlanarSectionCommand"
    )

    # Select mesh body
    app.executeTextCommand(
        "UI.EnableCommandInput infoBodyToModify"
    )
    selections.add(mesh)

    # Select construction plane
    app.executeTextCommand(
        "UI.EnableCommandInput planeSelectionInfo"
    )
    selections.add(plane)

    # Click OK
    app.executeTextCommand(
        "NuCommands.CommitCmd"
    )

    adsk.doEvents()

    selections.clear()
