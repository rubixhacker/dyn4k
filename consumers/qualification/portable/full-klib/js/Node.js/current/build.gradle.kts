tasks.register("development") {
    dependsOn(":qualificationEvidence")
}
tasks.register("production") {
    dependsOn(":qualificationEvidence")
}
