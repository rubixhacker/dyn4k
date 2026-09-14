[.[] | select(.payload | has("algorithm") or has("constructionAccepted"))] as $rows |
[$rows | group_by(.id | gsub("/s[012]/o[01234]"; ""))[] |
  . as $group | (map(select(.id | contains("/s1/o0/")))[0]) as $reference |
  $group[] | select(.id != $reference.id) | . as $actual |
  ["detected", "booleanOnlyDetected", "distanceAvailable", "constructionAccepted"][] as $field |
  select(($actual.payload | has($field)) and ($reference.payload | has($field))) |
  select($actual.payload[$field] != $reference.payload[$field]) |
  {id:$actual.id, referenceId:$reference.id, field:$field, reference:$reference.payload[$field], actual:$actual.payload[$field]}
] as $differences |
{status:"Exploratory scale/origin diagnostics; not port parity or supported-domain approval",
 rows:($rows|length), constructionRejections:[$rows[]|select(.payload.constructionAccepted==false)],
 overloadDisagreements:[$rows[]|select((.payload|has("detected")) and .payload.detected != .payload.booleanOnlyDetected)],
 discreteDifferences:$differences}
