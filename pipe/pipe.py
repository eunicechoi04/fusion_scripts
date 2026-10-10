import math
import traceback
import adsk.core
import adsk.fusion


app = adsk.core.Application.get()
ui = app.userInterface

# Side length of equilateral triangle, in mm
PIPE_SIZE_MM = 2.0


def run(context):
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)

        if not design:
            raise RuntimeError("Open a Fusion design first.")

        root = design.rootComponent

        # ------------------------------------------------------------
        # GET SELECTED PATHS
        # ------------------------------------------------------------

        selections = ui.activeSelections
        curves = []

        for i in range(selections.count):
            entity = selections.item(i).entity

            curve = adsk.fusion.SketchCurve.cast(entity)

            if curve:
                curves.append(curve)

        if len(curves) == 0:
            raise RuntimeError(
                "Select at least one sketch curve."
            )

        # Fusion's internal length unit is cm
        side = PIPE_SIZE_MM / 10.0

        sweeps = root.features.sweepFeatures
        planes = root.constructionPlanes
        sketches = root.sketches

        succeeded = 0
        failed = []

        # ------------------------------------------------------------
        # PIPE EACH CURVE
        # ------------------------------------------------------------

        for index, curve in enumerate(curves, start=1):

            try:
                # Create path
                path = adsk.fusion.Path.create(
                    curve,
                    adsk.fusion.ChainedCurveOptions.noChainedCurves
                )

                # ----------------------------------------------------
                # PLANE PERPENDICULAR TO PATH AT START
                # ----------------------------------------------------

                plane_input = planes.createInput()

                plane_input.setByDistanceOnPath(
                    curve,
                    adsk.core.ValueInput.createByReal(0.0)
                )

                plane = planes.add(plane_input)
                plane.name = f"Pipe Plane {index}"

                # ----------------------------------------------------
                # CREATE TRIANGLE
                # ----------------------------------------------------

                sketch = sketches.add(plane)
                sketch.name = f"Pipe Triangle {index}"

                # Equilateral triangle
                triangle_height = (
                    side * math.sqrt(3.0) / 2.0
                )

                # Center triangle on the path
                bottom = triangle_height / 3.0
                top = 2.0 * triangle_height / 3.0

                p1 = adsk.core.Point3D.create(
                    -side / 2.0,
                    -bottom,
                    0
                )

                p2 = adsk.core.Point3D.create(
                    side / 2.0,
                    -bottom,
                    0
                )

                p3 = adsk.core.Point3D.create(
                    0,
                    top,
                    0
                )

                lines = sketch.sketchCurves.sketchLines

                lines.addByTwoPoints(p1, p2)
                lines.addByTwoPoints(p2, p3)
                lines.addByTwoPoints(p3, p1)

                if sketch.profiles.count == 0:
                    raise RuntimeError(
                        "Could not create triangle profile."
                    )

                profile = sketch.profiles.item(0)

                # ----------------------------------------------------
                # SWEEP
                # ----------------------------------------------------

                sweep_input = sweeps.createInput(
                    profile,
                    path,
                    adsk.fusion.FeatureOperations.NewBodyFeatureOperation
                )

                sweep_input.orientation = (
                    adsk.fusion.SweepOrientationTypes
                    .PerpendicularOrientationType
                )

                sweep_feature = sweeps.add(
                    sweep_input
                )

                if sweep_feature.bodies.count == 0:
                    raise RuntimeError(
                        "Sweep did not create a body."
                    )

                # Hide construction geometry
                sketch.isVisible = False
                plane.isVisible = False

                succeeded += 1

            except Exception as e:
                failed.append(
                    f"Path {index}: {str(e)}"
                )

        # ------------------------------------------------------------
        # RESULT
        # ------------------------------------------------------------

        message = (
            f"Triangle size: {PIPE_SIZE_MM:g} mm\n"
            f"Pipes created: {succeeded}\n"
            f"Failed: {len(failed)}"
        )

        if failed:
            message += "\n\n" + "\n".join(failed)

        ui.messageBox(message)

    except Exception:
        ui.messageBox(
            "Failed:\n\n" +
            traceback.format_exc()
        )