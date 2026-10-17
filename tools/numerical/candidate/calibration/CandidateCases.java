import java.nio.file.Files;
import java.nio.file.Path;

public final class CandidateCases {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException("OUTPUT_DIRECTORY FAMILY CASE_FILTER");
        }
        String family = args[1];
        if (!family.equals("geometry") && !family.equals("motion") &&
            !family.equals("contacts") && !family.equals("joints") &&
            !family.equals("ccd") && !family.equals("long")) {
            throw new IllegalArgumentException("unrecognized fixture family: " + family);
        }
        Capture.open(Path.of(args[0]), args[2]);
        try {
            switch (family) {
                case "geometry" -> GeometryCases.runAll();
                case "joints" -> {
                    if (args[2].contains("P-JINT")) {
                        InteractionCases.runAll();
                    } else {
                        JointCases.runAll();
                        InteractionCases.runAll();
                    }
                }
                case "motion", "contacts", "ccd", "long" -> SceneCases.runAll();
            }
        } finally {
            Capture.close();
        }
        if ((family.equals("geometry") && Files.size(Path.of(args[0], "queries.jsonl")) == 0) ||
            (!family.equals("geometry") && Capture.counts.isEmpty() && Capture.failedCases == 0)) {
            throw new IllegalStateException("no fixture matched the filter");
        }
        if (Capture.failedCases != 0) throw new IllegalStateException(Capture.failedCases + " case(s) rejected; see summary.jsonl");
    }
}
