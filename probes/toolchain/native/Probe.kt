fun main() { val x = doubleArrayOf(1.0, 2.0); x[0] += x[1]; check(x[0] == 3.0); println("native-probe:3.0") }
