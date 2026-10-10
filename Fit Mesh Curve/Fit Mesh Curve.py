import adsk.core
import adsk.fusion
import traceback


SKETCH_NAME = "mesh 3"


def run(context):
    ui = None

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        sketch = root.sketches.itemByName(SKETCH_NAME)

        if not sketch:
            ui.messageBox(
                f'Could not find "{SKETCH_NAME}"'
            )
            return

        output = []

        output.append(f"Sketch: {sketch.name}")
        output.append(
            f"Sketch curves: {sketch.sketchCurves.count}"
        )

        # List every curve Fusion exposes
        for i in range(sketch.sketchCurves.count):

            curve = sketch.sketchCurves.item(i)

            output.append(
                f"{i}: "
                f"{curve.objectType}"
            )

        ui.messageBox("\n".join(output))

    except:
        if ui:
            ui.messageBox(
                "Failed:\n{}".format(
                    traceback.format_exc()
                )
            )