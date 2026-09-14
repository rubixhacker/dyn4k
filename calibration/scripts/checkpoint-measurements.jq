# Input: one audited trace, slurped. Diagnostics only; no acceptance tolerances.
def norm: (.[0]*.[0] + .[1]*.[1]) | sqrt;
def capratios:
  . as $j |
  reduce [["getSpringForce","getMaximumSpringForce","isMaximumSpringForceEnabled"],
          ["getSpringTorque","getMaximumSpringTorque","isMaximumSpringTorqueEnabled"],
          ["getMotorForce","getMaximumMotorForce","isMaximumMotorForceEnabled"],
          ["getMotorTorque","getMaximumMotorTorque","isMaximumMotorTorqueEnabled"]][] as $p
    ({}; if $j[$p[2]] == true and $j[$p[1]] > 0 then
      .[$p[0]+"AbsoluteCapRatio"] = (($j[$p[0]]|fabs)/$j[$p[1]])
    else . end);
def channels:
  .state as $s | $s.joints[0] as $j |
  ($j | with_entries(select(.value | type == "number"))) +
  {reactionForceMagnitude: ($j.reactionForce | norm)} + ($j|capratios) +
  (if $j.getCurrentLength1 != null then
    {pulleyWeightedLengthError: ($j.getCurrentLength1 + $j.getRatio*$j.getCurrentLength2 - $j.getLength)}
   else {} end) +
  (if $j.type == "org.dyn4j.dynamics.joint.MotorJoint" then
    ($s.bodies | map(select(.id == $j.bodies[0]))[0]) as $a |
    ($s.bodies | map(select(.id == $j.bodies[1]))[0]) as $b |
    $a.transform.getRotationAngle as $theta |
    {motorLinearTargetError: ([
      $b.worldCenter[0]-$a.worldCenter[0]-($theta|cos)*$j.getLinearTarget[0]+($theta|sin)*$j.getLinearTarget[1],
      $b.worldCenter[1]-$a.worldCenter[1]-($theta|sin)*$j.getLinearTarget[0]-($theta|cos)*$j.getLinearTarget[1]
    ]|norm),
     motorAngularTargetError: ($b.transform.getRotationAngle-$a.transform.getRotationAngle-$j.getAngularTarget)}
   else {} end);
.[0] as $input |
[.[] | select(.kind == "state") | {step, values: channels}] as $samples |
{
  id: $input.id,
  states: ($samples|length),
  scope: "Completed-state extrema and exact nonzero counts. No thresholds, cap activation verdict, or reference approval. Motor angular residual is unwrapped only within this small-angle fixture.",
  initial: ($input|channels),
  final: ($samples[-1] // null),
  channels: (reduce $samples[] as $sample ({};
    reduce ($sample.values|to_entries[]) as $kv (.;
      .[$kv.key] = (if .[$kv.key] == null then
        {minimum:$kv.value, maximum:$kv.value, minimumStep:$sample.step, maximumStep:$sample.step, nonzeroSamples:(if $kv.value != 0 then 1 else 0 end)}
      else .[$kv.key] |
        (if $kv.value < .minimum then .minimum=$kv.value | .minimumStep=$sample.step else . end) |
        (if $kv.value > .maximum then .maximum=$kv.value | .maximumStep=$sample.step else . end) |
        .nonzeroSamples += (if $kv.value != 0 then 1 else 0 end)
      end))))
}
