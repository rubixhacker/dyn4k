#!/usr/bin/env bash
set -euo pipefail
source_root=${1:-/tmp/dyn4j-numerical-baseline}
[[ $(git -C "$source_root" rev-parse HEAD) == 058bf6d982a0fb89b54050f929f6ea9dae53b714 ]] || { echo "Wrong upstream revision" >&2; exit 1; }
calibration_root=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$calibration_root/generated"
cp -R "$source_root/src/test/java/org" "$calibration_root/generated/"
find "$calibration_root/generated" -name '*.java' -print0 | xargs -0 perl -0777 -pi -e '
s/(package [^;]+;)/$1\nimport org.dyn4j.calibration.Bridge;/;
s/\bw\.step\(([^;]+)\);/Bridge.step(w, $1);/g;
s/this\.(sat|gjk)\.detect\(/Bridge.detect(this.$1, /g;
s/this\.detector\.getTimeOfImpact\(/Bridge.toi(this.detector, /g;
s/b\.integrateVelocity\(g, ts, s\);/Bridge.velocity(b, g, ts, s);/g;
s/b\.integratePosition\(ts, s\);/Bridge.position(b, ts, s);/g;
s/^(\t\t)([A-Za-z][A-Za-z0-9_]*\.(?:set\w+|translate|rotate|apply\w+|addBody|addJoint|removeJoint)\([^;\n]*\);)[ \t]*$/$1 . "Bridge.record(\"source-action\", \"" . ($2 =~ s\/"\/\\"\/gr) . "\");\n" . $1 . $2/gme;
'
# Only timed force/torque callbacks need completion capture; retain their decisions.
for cls in Force Torque; do
  perl -0777 -pi -e 's/time \+= elapsedTime;/time += elapsedTime; Bridge.record("completion-check", elapsedTime, time, time >= 2.0 \/ 60.0);/g' "$calibration_root/generated/org/dyn4j/simulation/${cls}SimulationTest.java"
done
{
  sed -n '1,/^package /p' "$source_root/src/test/java/org/dyn4j/simulation/DistanceJointSimulationTest.java" | sed '$d'
  echo 'import org.dyn4j.dynamics.*; import org.dyn4j.geometry.*; import org.dyn4j.world.World; import org.dyn4j.dynamics.joint.*; import junit.framework.TestCase;'
  echo 'public final class UpstreamScaleCases {'
  echo 'public static void runAll() { for(double scale:new double[]{0.01,1,100}) for(double[] o:new double[][]{{0,0},{1000,1000},{-1000,1000},{1000000,-1000000},{-1000000,1000000}}) {fixedDistance(scale,o[0],o[1]); motorWithAndWithoutLimits(scale,o[0],o[1]);}}'
  for spec in 'Distance fixedDistance' 'Revolute motorWithAndWithoutLimits'; do
    read -r cls method <<< "$spec"
    METHOD="$method" perl -0777 -ne '
      if(/public void \Q$ENV{METHOD}\E\(\) \{(.*?)\n\t\}/s) {
        $body=$1;
        $body =~ s/World<Body> w = new World<Body>\(\);/World<Body> w = new World<Body>(); SceneCases.scaleWorld(w,scale);/;
        $body =~ s/createRectangle\(10\.0, 0\.5\)/createRectangle(10.0*scale, 0.5*scale)/g;
        $body =~ s/createCircle\(0\.5\)/createCircle(0.5*scale)/g;
        $body =~ s/([gb]f)\.setFriction\(0\.0\);/$1.setRestitutionVelocity($1.getRestitutionVelocity()*scale); $1.setFriction(0.0);/g;
        $body =~ s/w.addBody\(g\);/g.translate(ox,oy); w.addBody(g);/;
        $body =~ s/b.translate\(0\.0, 2\.0\);/b.translate(ox, oy+2.0*scale);/;
        $body =~ s/setRestDistance\(10\.0\)/setRestDistance(10.0*scale)/;
        $body =~ s/setMaximumLinearCorrection\(0\.2\)/setMaximumLinearCorrection(0.2*scale)/;
        $body =~ s/setMaximumMotorTorque\(1000\)/setMaximumMotorTorque(1000*scale*scale*scale*scale)/;
        $body =~ s/TestCase.assertEquals\(2\.0, v1.distance\(v2\)\);/double exactInitialDistance = v1.distance(v2)\/scale;\n        String exactInitialStatus = "PASS";\n        try { TestCase.assertEquals(2.0, exactInitialDistance); }\n        catch (junit.framework.AssertionFailedError mismatch) { exactInitialStatus = "FAIL"; }\n        Capture.record("U-scale-fixedDistance-"+scale+"-"+ox+"-"+oy, "original-exact-initial-assertion", 2.0, exactInitialDistance, exactInitialStatus);/;
        $body =~ s/assertEquals\(v1.distance\(v2\), dj.getRestDistance\(\), 1e-5\)/assertEquals(v1.distance(v2)\/scale, dj.getRestDistance()\/scale, 1e-5)/;
        $body =~ s/(rj|dj)\.getReactionTorque\(invdt\)/$1.getReactionTorque(invdt)\/(scale*scale*scale*scale)/g;
        $body =~ s/dj.getReactionForce\(invdt\).([xy])/dj.getReactionForce(invdt).$1\/(scale*scale*scale)/g;
        $body =~ s/dj.getSpringForce\(invdt\)/dj.getSpringForce(invdt)\/(scale*scale*scale)/g;
        $body =~ s/w.step\((\d+)\);/Capture.run("U-scale-$ENV{METHOD}-"+scale+"-"+ox+"-"+oy,w,$1,1.0\/60.0,scale,ox,oy,n -> {});/g;
        print "public static void $ENV{METHOD}(double scale,double ox,double oy) {\nif (!Capture.accepts(\"U-scale-$ENV{METHOD}-\"+scale+\"-\"+ox+\"-\"+oy)) return;\n$body\n}\n";
      } else { die "missing method"; }
    ' "$source_root/src/test/java/org/dyn4j/simulation/${cls}JointSimulationTest.java"
  done
  echo '}'
} > "$calibration_root/src/UpstreamScaleCases.java"

# Preserve upstream code while normalizing trailing whitespace in the generated representative.
sed -i 's/[[:blank:]]*$//' "$calibration_root/src/UpstreamScaleCases.java"
