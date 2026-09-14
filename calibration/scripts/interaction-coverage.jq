# One slurped raw/derived trace. Exact bound equality is reported separately from
# distance within the baseline solver's own tolerance; neither approves a bound.
def magnitude: (.[0]*.[0]+.[1]*.[1])|sqrt;
.[0] as $input |
[.[]|select(.kind=="state")|. as $r|.state.joints[0] as $j|
 ($j.getLinearTranslation // $j.getCurrentDistance // $j.getAngularTranslation) as $q |
 (if $j.getLinearTranslation != null or $j.getCurrentDistance != null then $input.settings.getLinearTolerance else $input.settings.getAngularTolerance end) as $tol |
 (if $j|has("isLimitsEnabled") then $j.isLimitsEnabled else $j.isLowerLimitEnabled end) as $lo |
 (if $j|has("isLimitsEnabled") then $j.isLimitsEnabled else $j.isUpperLimitEnabled end) as $hi |
 ($j.getSpringForce // $j.getSpringTorque // 0) as $spring |
 ($j.getMotorForce // $j.getMotorTorque // 0) as $motor |
 {step:$r.step, coordinate:$q,lower:$j.getLowerLimit,upper:$j.getUpperLimit,
  spring:$spring,motor:$motor,
  axialLimitForce:(if $j.type=="org.dyn4j.dynamics.joint.PrismaticJoint" then
    $j.reactionForce[0]*$j.getAxis[0]+$j.reactionForce[1]*$j.getAxis[1]-$spring-$motor
    elif $j.type=="org.dyn4j.dynamics.joint.WheelJoint" then
    $j.reactionForce[0]*$j.getAxis[0]+$j.reactionForce[1]*$j.getAxis[1]-$spring
    else null end),
  exactLower:($lo==true and $q!=null and $q==$j.getLowerLimit),
  exactUpper:($hi==true and $q!=null and $q==$j.getUpperLimit),
  nearLower:($lo==true and $q!=null and (($q-$j.getLowerLimit)|fabs)<=$tol),
  nearUpper:($hi==true and $q!=null and (($q-$j.getUpperLimit)|fabs)<=$tol),
  bothForces:($j.isSpringEnabled==true and $j.isMotorEnabled==true and $spring!=0 and $motor!=0),
  slack:(if $j.getCurrentLength1!=null then $j.getCurrentLength1+$j.getRatio*$j.getCurrentLength2-$j.getLength else null end),
  slackEnabled:$j.isSlackEnabled}
] as $samples |
{id:$input.id,states:($samples|length),
 firstSimultaneousLower:([$samples[]|select(.bothForces and .exactLower)][0]//null),
 firstSimultaneousUpper:([$samples[]|select(.bothForces and .exactUpper)][0]//null),
 strongestSimultaneousLower:([$samples[]|select(.bothForces and .exactLower and .axialLimitForce!=null)]|max_by(.axialLimitForce|fabs)),
 strongestSimultaneousUpper:([$samples[]|select(.bothForces and .exactUpper and .axialLimitForce!=null)]|max_by(.axialLimitForce|fabs)),
 firstExactLower:([$samples[]|select(.exactLower)][0]//null),
 firstExactUpper:([$samples[]|select(.exactUpper)][0]//null),
 phases:([ [1,200],[201,400],[401,600] ]|map(. as $range |
 [$samples[]|select(.step>=$range[0] and .step<=$range[1])] as $phase |
 {steps:$range, samples:($phase|length),
  nonzeroSpring:([$phase[]|select(.spring!=0)]|length),
  nonzeroMotor:([$phase[]|select(.motor!=0)]|length),
  exactLower:([$phase[]|select(.exactLower)]|length),exactUpper:([$phase[]|select(.exactUpper)]|length),
  nearLower:([$phase[]|select(.nearLower)]|length),nearUpper:([$phase[]|select(.nearUpper)]|length),
  minimumSlack:([$phase[].slack|select(.!=null)]|min),
  enabledSlackBeyondSolverTolerance:([$phase[]|select(.slackEnabled==true and .slack!=null and .slack < -$input.settings.getLinearTolerance)]|length)
 }))}
