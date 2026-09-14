# Baseline diagnostic measurements

No numerical limits or invariant acceptance are established by this report.

Cases: 227. Reference catalog: 909. Partition: 1/4 (zero-based). Matched trajectory comparisons: 206. Missing references: 0.

## Coverage gaps

- CCD-world-circle-NONE-s0.01-o1000.0,1000.0-hz30: [no solved contact callbacks]
- CCD-world-pentagon-NONE-s0.01-o1000.0,1000.0-hz60: [no solved contact callbacks]
- C-stack-s0.01-o1000000.0,-1000000.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s0.01-o1000000.0,-1000000.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s0.01-o1000000.0,-1000000.0-hz60: [no solved contact callbacks]
- CCD-world-circle-NONE-s1.0-o0.0,0.0-hz30: [no solved contact callbacks]
- CCD-world-pentagon-NONE-s1.0-o0.0,0.0-hz60: [no solved contact callbacks]
- C-stack-s1.0-o1000.0,1000.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s1.0-o1000.0,1000.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s1.0-o1000.0,1000.0-hz60: [no solved contact callbacks]
- CCD-world-circle-NONE-s1.0-o1000000.0,-1000000.0-hz30: [no solved contact callbacks]
- CCD-world-pentagon-NONE-s1.0-o1000000.0,-1000000.0-hz60: [no solved contact callbacks]
- C-stack-s100.0-o0.0,0.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s100.0-o0.0,0.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s100.0-o0.0,0.0-hz60: [no solved contact callbacks]
- CCD-world-circle-NONE-s100.0-o-1000.0,1000.0-hz30: [no solved contact callbacks]
- CCD-world-pentagon-NONE-s100.0-o-1000.0,1000.0-hz60: [no solved contact callbacks]
- C-stack-s100.0-o-1000000.0,1000000.0-hz30: [wake action did not reach a sleeping top body]
- CCD-world-pentagon-NONE-s100.0-o-1000000.0,1000000.0-hz30: [no solved contact callbacks]
- CCD-world-circle-NONE-s100.0-o-1000000.0,1000000.0-hz60: [no solved contact callbacks]

## Largest normalized trajectory differences

Differences are componentwise maxima at common physical times, not acceptance failures. Values are normalized to nominal length/mass units. See JSON for every component maximum and the first differing sample.

| Case | Comparison | Largest difference | Quantity | Time (s) |
| --- | --- | ---: | --- | ---: |
| F-integrator-damping0.1-s0.01-o0.0,0.0-hz60 | scale/origin | 1.2434497875801753E-14 | b0.position.x | 8.0 |
| C-bounce-e1.0-s0.01-o0.0,0.0-hz30 | scale/origin | 0.0035881836858245903 | b1.position.x | 1.8 |
| C-bounce-e1.0-s0.01-o0.0,0.0-hz30 | timestep | 11.433333333333337 | b1.velocity.y | 9.033333333333333 |
| CCD-world-pentagon-ALL-s0.01-o0.0,0.0-hz30 | scale/origin | 2.773169572805404E-11 | b1.position.x | 0.03333333333333333 |
| CCD-world-pentagon-ALL-s0.01-o0.0,0.0-hz30 | timestep | 94.24777960769379 | b1.angularVelocity | 0.1 |
| C-bounce-e0.0-s0.01-o0.0,0.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-ALL-s0.01-o0.0,0.0-hz60 | scale/origin | 0.00500390554821388 | b1.position.y | 0.016666666666666666 |
| L-spring-damperfalse-s0.01-o0.0,0.0-hz60 | scale/origin | 6.821210263296962E-13 | j0.reactionForce.y | 0.08333333333333333 |
| C-bounce-e1.0-s0.01-o0.0,0.0-hz120 | scale/origin | 0.00358818368455695 | b1.position.x | 1.675 |
| C-bounce-e1.0-s0.01-o0.0,0.0-hz120 | timestep | 10.943333333333335 | b1.velocity.y | 1.6833333333333333 |
| CCD-world-pentagon-ALL-s0.01-o0.0,0.0-hz120 | scale/origin | 5.2703815270338517E-11 | b1.position.x | 0.041666666666666664 |
| CCD-world-pentagon-ALL-s0.01-o0.0,0.0-hz120 | timestep | 168.49555921538757 | b1.angularVelocity | 0.016666666666666666 |
| F-integrator-damping0.0-s0.01-o1000.0,1000.0-hz60 | scale/origin | 3.030361739320142E-9 | b0.position.x | 10.0 |
| C-bounce-e0.5-s0.01-o1000.0,1000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e0.5-s0.01-o1000.0,1000.0-hz30 | timestep | 8.330000000000002 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s0.01-o1000.0,1000.0-hz30 | scale/origin | 5.3660187404602766E-11 | b1.position.y | 1.0 |
| CCD-world-circle-NONE-s0.01-o1000.0,1000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-dampertrue-s0.01-o1000.0,1000.0-hz30 | scale/origin | 3.785066691824011E-9 | j0.reactionForce.y | 0.6333333333333333 |
| L-spring-dampertrue-s0.01-o1000.0,1000.0-hz30 | timestep | 300.58670070604546 | j0.reactionForce.y | 0.03333333333333333 |
| C-stack-s0.01-o1000.0,1000.0-hz60 | scale/origin | 2183.554415176068 | b9.position.y | 562.3333333333334 |
| CCD-world-pentagon-NONE-s0.01-o1000.0,1000.0-hz60 | scale/origin | 1.0822986951097846E-10 | b1.position.y | 1.0 |
| C-bounce-e0.5-s0.01-o1000.0,1000.0-hz120 | scale/origin | 0.25861112084694104 | b1.velocity.y | 3.3 |
| C-bounce-e0.5-s0.01-o1000.0,1000.0-hz120 | timestep | 4.103750000000001 | b1.velocity.y | 1.1333333333333333 |
| CCD-world-circle-NONE-s0.01-o1000.0,1000.0-hz120 | scale/origin | 1.6236553768145257E-11 | b1.position.y | 0.25 |
| CCD-world-circle-NONE-s0.01-o1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-dampertrue-s0.01-o1000.0,1000.0-hz120 | scale/origin | 1.6274515957093172E-8 | j0.reactionForce.y | 0.2916666666666667 |
| L-spring-dampertrue-s0.01-o1000.0,1000.0-hz120 | timestep | 286.4818543665849 | j0.reactionForce.y | 0.05 |
| C-bounce-e0.0-s0.01-o-1000.0,1000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e0.0-s0.01-o-1000.0,1000.0-hz30 | timestep | 5.553333333333335 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s0.01-o-1000.0,1000.0-hz30 | scale/origin | 1.9497182298326216E-9 | b1.position.x | 0.03333333333333333 |
| CCD-world-circle-ALL-s0.01-o-1000.0,1000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-damperfalse-s0.01-o-1000.0,1000.0-hz30 | scale/origin | 4.383757482018247E-9 | j0.reactionForce.y | 0.5 |
| L-spring-damperfalse-s0.01-o-1000.0,1000.0-hz30 | timestep | 395.6843085543529 | j0.reactionForce.y | 0.06666666666666667 |
| C-bounce-e1.0-s0.01-o-1000.0,1000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-pentagon-ALL-s0.01-o-1000.0,1000.0-hz60 | scale/origin | 6.036735555881023E-9 | b1.velocity.y | 0.03333333333333333 |
| C-bounce-e0.0-s0.01-o-1000.0,1000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e0.0-s0.01-o-1000.0,1000.0-hz120 | timestep | 0.021777777783427155 | b1.position.y | 0.5333333333333333 |
| CCD-world-circle-ALL-s0.01-o-1000.0,1000.0-hz120 | scale/origin | 1.9497182298326216E-9 | b1.position.x | 0.008333333333333333 |
| CCD-world-circle-ALL-s0.01-o-1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-damperfalse-s0.01-o-1000.0,1000.0-hz120 | scale/origin | 2.6197321201237855E-8 | j0.reactionForce.y | 0.725 |
| L-spring-damperfalse-s0.01-o-1000.0,1000.0-hz120 | timestep | 439.2351714903537 | j0.reactionForce.y | 0.05 |
| C-slide-s0.01-o1000000.0,-1000000.0-hz60 | scale/origin | 2.49470284430231E-8 | b1.position.x | 0.7166666666666667 |
| C-stack-s0.01-o1000000.0,-1000000.0-hz30 | scale/origin | 5.7528190600487505 | b10.rotationIncrementSum | 600.0 |
| C-stack-s0.01-o1000000.0,-1000000.0-hz30 | timestep | 25193.12612671638 | b10.position.y | 439.3666666666667 |
| CCD-world-pentagon-NONE-s0.01-o1000000.0,-1000000.0-hz30 | scale/origin | 5.494803190231323E-8 | b1.position.y | 1.0 |
| CCD-world-pentagon-NONE-s0.01-o1000000.0,-1000000.0-hz30 | timestep | 60.000000055879354 | b1.position.y | 1.0 |
| C-bounce-e0.5-s0.01-o1000000.0,-1000000.0-hz60 | scale/origin | 8.330000000000002 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s0.01-o1000000.0,-1000000.0-hz60 | scale/origin | 1.1082738637924194E-7 | b1.position.y | 1.0 |
| L-spring-dampertrue-s0.01-o1000000.0,-1000000.0-hz60 | scale/origin | 8.732592177708613E-6 | j0.reactionForce.y | 0.7833333333333333 |
| C-stack-s0.01-o1000000.0,-1000000.0-hz120 | scale/origin | 1.1079433555958678 | b7.velocity.y | 0.15 |
| C-stack-s0.01-o1000000.0,-1000000.0-hz120 | timestep | 19282.629237300716 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s0.01-o1000000.0,-1000000.0-hz120 | scale/origin | 3.8278134995017865E-8 | b1.orientation | 0.2 |
| CCD-world-pentagon-NONE-s0.01-o1000000.0,-1000000.0-hz120 | timestep | 120.00000000000001 | b1.velocity.y | 0.016666666666666666 |
| F-integrator-damping0.1-s0.01-o-1000000.0,1000000.0-hz60 | scale/origin | 8.686990415895934E-8 | b0.position.x | 4.316666666666666 |
| C-bounce-e1.0-s0.01-o-1000000.0,1000000.0-hz30 | scale/origin | 13.720000000000002 | b1.velocity.y | 8.866666666666667 |
| C-bounce-e1.0-s0.01-o-1000000.0,1000000.0-hz30 | timestep | 16.00666666666667 | b1.velocity.y | 8.566666666666666 |
| CCD-world-pentagon-ALL-s0.01-o-1000000.0,1000000.0-hz30 | scale/origin | 1.1759835444324906E-7 | b1.orientation | 0.5666666666666667 |
| CCD-world-pentagon-ALL-s0.01-o-1000000.0,1000000.0-hz30 | timestep | 94.24777960769384 | b1.angularVelocity | 0.06666666666666667 |
| C-bounce-e0.0-s0.01-o-1000000.0,1000000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-ALL-s0.01-o-1000000.0,1000000.0-hz60 | scale/origin | 1.5057098193271834E-8 | b1.position.y | 0.26666666666666666 |
| L-spring-damperfalse-s0.01-o-1000000.0,1000000.0-hz60 | scale/origin | 1.181813366236804E-5 | j0.reactionForce.y | 0.9833333333333333 |
| C-bounce-e1.0-s0.01-o-1000000.0,1000000.0-hz120 | scale/origin | 10.94333333333334 | b1.velocity.y | 1.6833333333333333 |
| C-bounce-e1.0-s0.01-o-1000000.0,1000000.0-hz120 | timestep | 11.433333333333337 | b1.velocity.y | 1.7166666666666666 |
| CCD-world-pentagon-ALL-s0.01-o-1000000.0,1000000.0-hz120 | scale/origin | 9.827539670936858E-7 | b1.position.y | 1.0 |
| CCD-world-pentagon-ALL-s0.01-o-1000000.0,1000000.0-hz120 | timestep | 168.4955592153876 | b1.angularVelocity | 0.016666666666666666 |
| C-bounce-e0.5-s1.0-o0.0,0.0-hz30 | timestep | 8.330000000000002 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s1.0-o0.0,0.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| L-spring-dampertrue-s1.0-o0.0,0.0-hz30 | timestep | 300.58670071081946 | j0.reactionForce.y | 0.03333333333333333 |
| C-bounce-e0.5-s1.0-o0.0,0.0-hz120 | timestep | 4.103750000000002 | b1.velocity.y | 1.1333333333333333 |
| CCD-world-circle-NONE-s1.0-o0.0,0.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-dampertrue-s1.0-o0.0,0.0-hz120 | timestep | 286.48185437191086 | j0.reactionForce.y | 0.05 |
| C-slide-s1.0-o1000.0,1000.0-hz60 | scale/origin | 1.425526363618701E-13 | b1.position.x | 1.1666666666666667 |
| C-stack-s1.0-o1000.0,1000.0-hz30 | scale/origin | 4.1048230130735774E-5 | b10.orientation | 600.0 |
| C-stack-s1.0-o1000.0,1000.0-hz30 | timestep | 24363.203176045445 | b10.position.y | 425.53333333333336 |
| CCD-world-pentagon-NONE-s1.0-o1000.0,1000.0-hz30 | scale/origin | 9.590581219480213E-18 | b1.position.x | 0.1 |
| CCD-world-pentagon-NONE-s1.0-o1000.0,1000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| C-bounce-e0.5-s1.0-o1000.0,1000.0-hz60 | scale/origin | 0.0035881836822277227 | b1.position.x | 1.1333333333333333 |
| CCD-world-circle-NONE-s1.0-o1000.0,1000.0-hz60 | scale/origin | 0 | none | 0 |
| L-spring-dampertrue-s1.0-o1000.0,1000.0-hz60 | scale/origin | 6.91460260359919E-11 | j0.reactionForce.y | 0.6333333333333333 |
| C-stack-s1.0-o1000.0,1000.0-hz120 | scale/origin | 0.20187026115684964 | b10.velocity.x | 300.5 |
| C-stack-s1.0-o1000.0,1000.0-hz120 | timestep | 20942.481001515353 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s1.0-o1000.0,1000.0-hz120 | scale/origin | 5.238587341693801E-13 | b1.orientation | 0.5083333333333333 |
| CCD-world-pentagon-NONE-s1.0-o1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| F-integrator-damping0.1-s1.0-o-1000.0,1000.0-hz60 | scale/origin | 8.01136934569513E-13 | b0.position.x | 6.383333333333334 |
| C-bounce-e1.0-s1.0-o-1000.0,1000.0-hz30 | scale/origin | 0.005000000004074856 | b1.position.y | 2.8666666666666667 |
| C-bounce-e1.0-s1.0-o-1000.0,1000.0-hz30 | timestep | 11.433333333333337 | b1.velocity.y | 9.0 |
| CCD-world-pentagon-ALL-s1.0-o-1000.0,1000.0-hz30 | scale/origin | 6.9229086636667646E-12 | b1.position.x | 0.03333333333333333 |
| CCD-world-pentagon-ALL-s1.0-o-1000.0,1000.0-hz30 | timestep | 94.24777960769381 | b1.angularVelocity | 0.06666666666666667 |
| C-bounce-e0.0-s1.0-o-1000.0,1000.0-hz60 | scale/origin | 0.003588183677105949 | b1.position.x | 0.5666666666666667 |
| CCD-world-circle-ALL-s1.0-o-1000.0,1000.0-hz60 | scale/origin | 8.95061109462308E-11 | b1.position.x | 0.5333333333333333 |
| L-spring-damperfalse-s1.0-o-1000.0,1000.0-hz60 | scale/origin | 1.3707524004757943E-10 | j0.reactionForce.y | 0.36666666666666664 |
| C-bounce-e1.0-s1.0-o-1000.0,1000.0-hz120 | scale/origin | 0.003588183684974197 | b1.position.x | 1.675 |
| C-bounce-e1.0-s1.0-o-1000.0,1000.0-hz120 | timestep | 10.94333333333334 | b1.velocity.y | 1.6833333333333333 |
| CCD-world-pentagon-ALL-s1.0-o-1000.0,1000.0-hz120 | scale/origin | 3.361577682881034E-11 | b1.velocity.y | 0.016666666666666666 |
| CCD-world-pentagon-ALL-s1.0-o-1000.0,1000.0-hz120 | timestep | 168.4955592153876 | b1.angularVelocity | 0.016666666666666666 |
| F-integrator-damping0.0-s1.0-o1000000.0,-1000000.0-hz60 | scale/origin | 3.054272568192573E-8 | b0.position.x | 10.0 |
| C-bounce-e0.5-s1.0-o1000000.0,-1000000.0-hz30 | scale/origin | 0.005000000154908979 | b1.position.y | 5.0 |
| C-bounce-e0.5-s1.0-o1000000.0,-1000000.0-hz30 | timestep | 8.330000000000002 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s1.0-o1000000.0,-1000000.0-hz30 | scale/origin | 0 | none | 0 |
| CCD-world-circle-NONE-s1.0-o1000000.0,-1000000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| L-spring-dampertrue-s1.0-o1000000.0,-1000000.0-hz30 | scale/origin | 3.851826591017016E-8 | j0.reactionForce.y | 0.23333333333333334 |
| L-spring-dampertrue-s1.0-o1000000.0,-1000000.0-hz30 | timestep | 300.58670066092157 | j0.reactionForce.y | 0.03333333333333333 |
| C-stack-s1.0-o1000000.0,-1000000.0-hz60 | scale/origin | 514.6930369359143 | b9.position.y | 569.05 |
| CCD-world-pentagon-NONE-s1.0-o1000000.0,-1000000.0-hz60 | scale/origin | 8.830292603032948E-18 | b1.position.x | 0.7166666666666667 |
| C-bounce-e0.5-s1.0-o1000000.0,-1000000.0-hz120 | scale/origin | 0.25861112084694104 | b1.velocity.y | 3.3 |
| C-bounce-e0.5-s1.0-o1000000.0,-1000000.0-hz120 | timestep | 4.103750000000002 | b1.velocity.y | 1.1333333333333333 |
| CCD-world-circle-NONE-s1.0-o1000000.0,-1000000.0-hz120 | scale/origin | 120.0 | b1.velocity.y | 0.016666666666666666 |
| CCD-world-circle-NONE-s1.0-o1000000.0,-1000000.0-hz120 | timestep | 0 | none | 0 |
| L-spring-dampertrue-s1.0-o1000000.0,-1000000.0-hz120 | scale/origin | 1.6464416452421915E-7 | j0.reactionForce.y | 0.25 |
| L-spring-dampertrue-s1.0-o1000000.0,-1000000.0-hz120 | timestep | 286.4818544120991 | j0.reactionForce.y | 0.05 |
| C-bounce-e0.0-s1.0-o-1000000.0,1000000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e0.0-s1.0-o-1000000.0,1000000.0-hz30 | timestep | 5.5533333333333355 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s1.0-o-1000000.0,1000000.0-hz30 | scale/origin | 1.9497182298326216E-9 | b1.position.x | 0.03333333333333333 |
| CCD-world-circle-ALL-s1.0-o-1000000.0,1000000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-damperfalse-s1.0-o-1000000.0,1000000.0-hz30 | scale/origin | 5.1594244140917844E-8 | j0.reactionForce.y | 0.5 |
| L-spring-damperfalse-s1.0-o-1000000.0,1000000.0-hz30 | timestep | 395.68430863332935 | j0.reactionForce.y | 0.06666666666666667 |
| C-bounce-e1.0-s1.0-o-1000000.0,1000000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-pentagon-ALL-s1.0-o-1000000.0,1000000.0-hz60 | scale/origin | 5.6806960913036164E-8 | b1.velocity.y | 0.03333333333333333 |
| C-bounce-e0.0-s1.0-o-1000000.0,1000000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e0.0-s1.0-o-1000000.0,1000000.0-hz120 | timestep | 0.021777777932584286 | b1.position.y | 0.5333333333333333 |
| CCD-world-circle-ALL-s1.0-o-1000000.0,1000000.0-hz120 | scale/origin | 1.9497182298326216E-9 | b1.position.x | 0.008333333333333333 |
| CCD-world-circle-ALL-s1.0-o-1000000.0,1000000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-damperfalse-s1.0-o-1000000.0,1000000.0-hz120 | scale/origin | 3.1427427753250026E-7 | j0.reactionForce.y | 1.1666666666666667 |
| L-spring-damperfalse-s1.0-o-1000000.0,1000000.0-hz120 | timestep | 439.2351715339644 | j0.reactionForce.y | 0.05 |
| C-slide-s100.0-o0.0,0.0-hz60 | scale/origin | 4.884981308350689E-15 | b1.velocity.x | 0.55 |
| C-stack-s100.0-o0.0,0.0-hz30 | scale/origin | 7.046673999866471E-8 | b10.rotationIncrementSum | 600.0 |
| C-stack-s100.0-o0.0,0.0-hz30 | timestep | 24363.20317592706 | b10.position.y | 425.53333333333336 |
| CCD-world-pentagon-NONE-s100.0-o0.0,0.0-hz30 | scale/origin | 1.2275932041159218E-18 | b1.position.x | 0.6666666666666666 |
| CCD-world-pentagon-NONE-s100.0-o0.0,0.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| C-bounce-e0.5-s100.0-o0.0,0.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-NONE-s100.0-o0.0,0.0-hz60 | scale/origin | 0 | none | 0 |
| L-spring-dampertrue-s100.0-o0.0,0.0-hz60 | scale/origin | 5.648814749292796E-13 | j0.reactionForce.y | 0.25 |
| C-stack-s100.0-o0.0,0.0-hz120 | scale/origin | 0.4012015087755686 | b10.position.x | 595.5 |
| C-stack-s100.0-o0.0,0.0-hz120 | timestep | 20942.47921434144 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s100.0-o0.0,0.0-hz120 | scale/origin | 3.354453646278369E-13 | b1.angularVelocity | 0.016666666666666666 |
| CCD-world-pentagon-NONE-s100.0-o0.0,0.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.03333333333333333 |
| F-integrator-damping0.1-s100.0-o1000.0,1000.0-hz60 | scale/origin | 3.7214675785435247E-13 | b0.rotationIncrementSum | 3.3333333333333335 |
| C-bounce-e1.0-s100.0-o1000.0,1000.0-hz30 | scale/origin | 0.005824242582550088 | b1.position.x | 5.9 |
| C-bounce-e1.0-s100.0-o1000.0,1000.0-hz30 | timestep | 11.433333333333334 | b1.velocity.y | 9.233333333333333 |
| CCD-world-pentagon-ALL-s100.0-o1000.0,1000.0-hz30 | scale/origin | 6.9229086636667646E-12 | b1.position.x | 0.03333333333333333 |
| CCD-world-pentagon-ALL-s100.0-o1000.0,1000.0-hz30 | timestep | 94.24777960769379 | b1.angularVelocity | 0.1 |
| C-bounce-e0.0-s100.0-o1000.0,1000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-ALL-s100.0-o1000.0,1000.0-hz60 | scale/origin | 3.568298245402781E-12 | b1.position.x | 0.016666666666666666 |
| L-spring-damperfalse-s100.0-o1000.0,1000.0-hz60 | scale/origin | 2.5011104298755527E-12 | j0.reactionForce.y | 0.16666666666666666 |
| C-bounce-e1.0-s100.0-o1000.0,1000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e1.0-s100.0-o1000.0,1000.0-hz120 | timestep | 10.943333333333335 | b1.velocity.y | 1.6833333333333333 |
| CCD-world-pentagon-ALL-s100.0-o1000.0,1000.0-hz120 | scale/origin | 1.3673119927948285E-11 | b1.position.x | 0.03333333333333333 |
| CCD-world-pentagon-ALL-s100.0-o1000.0,1000.0-hz120 | timestep | 168.49555921538757 | b1.angularVelocity | 0.016666666666666666 |
| F-integrator-damping0.0-s100.0-o-1000.0,1000.0-hz60 | scale/origin | 2.184918912462308E-13 | b0.position.x | 9.983333333333333 |
| C-bounce-e0.5-s100.0-o-1000.0,1000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e0.5-s100.0-o-1000.0,1000.0-hz30 | timestep | 8.33 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-NONE-s100.0-o-1000.0,1000.0-hz30 | scale/origin | 0 | none | 0 |
| CCD-world-circle-NONE-s100.0-o-1000.0,1000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| L-spring-dampertrue-s100.0-o-1000.0,1000.0-hz30 | scale/origin | 6.109501264812446E-13 | j0.reactionForce.y | 0.8666666666666667 |
| L-spring-dampertrue-s100.0-o-1000.0,1000.0-hz30 | timestep | 300.5867007108185 | j0.reactionForce.y | 0.03333333333333333 |
| C-stack-s100.0-o-1000.0,1000.0-hz60 | scale/origin | 802.4966458921481 | b9.position.y | 569.05 |
| CCD-world-pentagon-NONE-s100.0-o-1000.0,1000.0-hz60 | scale/origin | 8.830292603032948E-18 | b1.position.x | 0.7166666666666667 |
| C-bounce-e0.5-s100.0-o-1000.0,1000.0-hz120 | scale/origin | 0.24416259765625023 | b1.velocity.y | 1.8 |
| C-bounce-e0.5-s100.0-o-1000.0,1000.0-hz120 | timestep | 4.103749999999999 | b1.velocity.y | 1.1333333333333333 |
| CCD-world-circle-NONE-s100.0-o-1000.0,1000.0-hz120 | scale/origin | 1.3642420517097575E-13 | b1.angularVelocity | 0.025 |
| CCD-world-circle-NONE-s100.0-o-1000.0,1000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-dampertrue-s100.0-o-1000.0,1000.0-hz120 | scale/origin | 3.872675834529216E-12 | j0.reactionForce.y | 0.8833333333333333 |
| L-spring-dampertrue-s100.0-o-1000.0,1000.0-hz120 | timestep | 286.48185437190983 | j0.reactionForce.y | 0.05 |
| C-bounce-e0.0-s100.0-o1000000.0,-1000000.0-hz30 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.5666666666666667 |
| C-bounce-e0.0-s100.0-o1000000.0,-1000000.0-hz30 | timestep | 5.553333333333334 | b1.velocity.y | 0.5666666666666667 |
| CCD-world-circle-ALL-s100.0-o1000000.0,-1000000.0-hz30 | scale/origin | 4.5843795722958656E-10 | b1.position.x | 0.03333333333333333 |
| CCD-world-circle-ALL-s100.0-o1000000.0,-1000000.0-hz30 | timestep | 60.0 | b1.velocity.y | 0.03333333333333333 |
| L-spring-damperfalse-s100.0-o1000000.0,-1000000.0-hz30 | scale/origin | 4.731331906121516E-10 | j0.reactionForce.y | 0.5666666666666667 |
| L-spring-damperfalse-s100.0-o1000000.0,-1000000.0-hz30 | timestep | 395.6843085579885 | j0.reactionForce.y | 0.06666666666666667 |
| C-bounce-e1.0-s100.0-o1000000.0,-1000000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-pentagon-ALL-s100.0-o1000000.0,-1000000.0-hz60 | scale/origin | 3.0323832334033796E-10 | b1.position.y | 1.0 |
| C-bounce-e0.0-s100.0-o1000000.0,-1000000.0-hz120 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| C-bounce-e0.0-s100.0-o1000000.0,-1000000.0-hz120 | timestep | 0.021777777777751917 | b1.position.y | 0.5333333333333333 |
| CCD-world-circle-ALL-s100.0-o1000000.0,-1000000.0-hz120 | scale/origin | 4.5843795722958656E-10 | b1.position.x | 0.008333333333333333 |
| CCD-world-circle-ALL-s100.0-o1000000.0,-1000000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.016666666666666666 |
| L-spring-damperfalse-s100.0-o1000000.0,-1000000.0-hz120 | scale/origin | 2.492821171706794E-9 | j0.reactionForce.y | 0.8166666666666667 |
| L-spring-damperfalse-s100.0-o1000000.0,-1000000.0-hz120 | timestep | 439.2351714854011 | j0.reactionForce.y | 0.05 |
| C-slide-s100.0-o-1000000.0,1000000.0-hz60 | scale/origin | 1.2949641359227826E-12 | b1.position.x | 0.6 |
| C-stack-s100.0-o-1000000.0,1000000.0-hz30 | scale/origin | 4.937378610259113E-4 | b10.orientation | 600.0 |
| C-stack-s100.0-o-1000000.0,1000000.0-hz30 | timestep | 24363.203169508055 | b10.position.y | 425.53333333333336 |
| CCD-world-pentagon-NONE-s100.0-o-1000000.0,1000000.0-hz30 | scale/origin | 9.590581219480213E-18 | b1.position.x | 0.1 |
| CCD-world-pentagon-NONE-s100.0-o-1000000.0,1000000.0-hz30 | timestep | 60.0 | b1.position.y | 1.0 |
| C-bounce-e0.5-s100.0-o-1000000.0,1000000.0-hz60 | scale/origin | 0.0035881836770187635 | b1.position.x | 0.55 |
| CCD-world-circle-NONE-s100.0-o-1000000.0,1000000.0-hz60 | scale/origin | 0 | none | 0 |
| L-spring-dampertrue-s100.0-o-1000000.0,1000000.0-hz60 | scale/origin | 8.662941353848597E-10 | j0.reactionForce.y | 0.4666666666666667 |
| C-stack-s100.0-o-1000000.0,1000000.0-hz120 | scale/origin | 0.20186411320221703 | b10.velocity.x | 300.5 |
| C-stack-s100.0-o-1000000.0,1000000.0-hz120 | timestep | 20942.480946070642 | b10.position.y | 600.0 |
| CCD-world-pentagon-NONE-s100.0-o-1000000.0,1000000.0-hz120 | scale/origin | 9.698686298520443E-12 | b1.orientation | 0.48333333333333334 |
| CCD-world-pentagon-NONE-s100.0-o-1000000.0,1000000.0-hz120 | timestep | 120.0 | b1.velocity.y | 0.03333333333333333 |
| U-scale-motorWithAndWithoutLimits-0.01-0.0-0.0 | scale/origin | 1.7763568394002505E-15 | j0.reactionTorque | 0.5333333333333333 |
| U-scale-motorWithAndWithoutLimits-0.01-1000.0-1000.0 | scale/origin | 1.8189894035458565E-12 | b1.position.y | 0.03333333333333333 |
| U-scale-motorWithAndWithoutLimits-0.01--1000.0-1000.0 | scale/origin | 1.8189894035458565E-12 | b1.position.y | 0.016666666666666666 |
| U-scale-fixedDistance-0.01-1000000.0--1000000.0 | scale/origin | 2.3283064365386963E-9 | b1.position.y | 0.016666666666666666 |
| U-scale-motorWithAndWithoutLimits-0.01-1000000.0--1000000.0 | scale/origin | 1.862645149230957E-9 | b1.position.y | 0.55 |
| U-scale-motorWithAndWithoutLimits-0.01--1000000.0-1000000.0 | scale/origin | 1.862645149230957E-9 | b1.position.y | 0.5333333333333333 |
| U-scale-motorWithAndWithoutLimits-1.0-1000.0-1000.0 | scale/origin | 0 | none | 0 |
| U-scale-fixedDistance-1.0--1000.0-1000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-1.0--1000.0-1000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-1.0-1000000.0--1000000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-1.0--1000000.0-1000000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-100.0-0.0-0.0 | scale/origin | 4.440892098500626E-16 | j0.reactionTorque | 0.016666666666666666 |
| U-scale-fixedDistance-100.0-1000.0-1000.0 | scale/origin | 0 | none | 0 |
| U-scale-motorWithAndWithoutLimits-100.0-1000.0-1000.0 | scale/origin | 1.7763568394002505E-15 | j0.reactionTorque | 1.0333333333333334 |
| U-scale-motorWithAndWithoutLimits-100.0--1000.0-1000.0 | scale/origin | 1.7763568394002505E-15 | j0.reactionTorque | 0.5333333333333333 |
| U-scale-motorWithAndWithoutLimits-100.0-1000000.0--1000000.0 | scale/origin | 3.2886504186536647E-15 | j0.reactionTorque | 0.2833333333333333 |
| U-scale-motorWithAndWithoutLimits-100.0--1000000.0-1000000.0 | scale/origin | 4.440892098500626E-16 | j0.reactionTorque | 0.016666666666666666 |

## Spring mechanical-energy diagnostics

E = Σ(½mv² + ½Iω² − m g·(x−O)) + ½k(d−rest)². Source: pinned DistanceJoint.updateSpringCoefficients uses reduced mass and k=mReduced(2πf)². Initial stiffness is calculated from initial masses/frequency because upstream computes the effective getter at first initialization. Captured stiffness is checked against that value. Energy drift is a baseline diagnostic, including undamped numerical dissipation; damped cases intentionally dissipate energy. No conservation bound is approved.

- L-spring-damperfalse-s0.01-o0.0,0.0-hz60: initial energy 9.922008537695937E-6; max absolute drift 9.922008537695935E-6; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s0.01-o1000.0,1000.0-hz30: initial energy 9.922008537732036E-6; max absolute drift 9.922008537732036E-6; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s0.01-o1000.0,1000.0-hz120: initial energy 9.922008537732036E-6; max absolute drift 9.922008537732036E-6; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s0.01-o-1000.0,1000.0-hz30: initial energy 9.922008537732036E-6; max absolute drift 9.922008537732034E-6; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s0.01-o-1000.0,1000.0-hz120: initial energy 9.922008537732036E-6; max absolute drift 9.922008537719081E-6; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s0.01-o1000000.0,-1000000.0-hz60: initial energy 9.922008500733575E-6; max absolute drift 9.922008500733575E-6; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s0.01-o-1000000.0,1000000.0-hz60: initial energy 9.922008500733575E-6; max absolute drift 9.922008500733575E-6; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o0.0,0.0-hz30: initial energy 992.2008537695941; max absolute drift 992.2008537695941; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o0.0,0.0-hz120: initial energy 992.2008537695941; max absolute drift 992.200853769594; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o1000.0,1000.0-hz60: initial energy 992.2008537695941; max absolute drift 992.2008537695941; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s1.0-o-1000.0,1000.0-hz60: initial energy 992.2008537695941; max absolute drift 992.200853769594; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o1000000.0,-1000000.0-hz30: initial energy 992.2008537695941; max absolute drift 992.2008537695941; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s1.0-o1000000.0,-1000000.0-hz120: initial energy 992.2008537695941; max absolute drift 992.200853769594; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s1.0-o-1000000.0,1000000.0-hz30: initial energy 992.2008537695941; max absolute drift 992.2008537695939; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s1.0-o-1000000.0,1000000.0-hz120: initial energy 992.2008537695941; max absolute drift 992.2008537682988; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o0.0,0.0-hz60: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s100.0-o1000.0,1000.0-hz60: initial energy 9.922008537695943E10; max absolute drift 9.922008537695941E10; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o-1000.0,1000.0-hz30: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o-1000.0,1000.0-hz120: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s100.0-o1000000.0,-1000000.0-hz30: initial energy 9.922008537695943E10; max absolute drift 9.922008537695941E10; max stiffness discrepancy 0.0.
- L-spring-damperfalse-s100.0-o1000000.0,-1000000.0-hz120: initial energy 9.922008537695943E10; max absolute drift 9.922008537682988E10; max stiffness discrepancy 0.0.
- L-spring-dampertrue-s100.0-o-1000000.0,1000000.0-hz60: initial energy 9.922008537695943E10; max absolute drift 9.922008537695943E10; max stiffness discrepancy 0.0.

Comparisons cover bodies and selected joint fields, not contact identity alignment or every joint mode/cap. CCD centre crossing is geometric observation, not by itself a solver verdict. See JSON for exact actions, source summaries, missing references and first differences.
