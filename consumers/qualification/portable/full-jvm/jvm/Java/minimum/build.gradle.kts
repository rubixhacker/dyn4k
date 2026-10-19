tasks.register("default") {
    dependsOn(":qualificationEvidence")
}

tasks.register("no-optimize") {
    dependsOn(":qualificationEvidence")
}
