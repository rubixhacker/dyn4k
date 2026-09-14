import java.nio.file.Path;
public final class Main {
    public static void main(String[] args) throws Exception {
        if(args.length==1&&args[0].equals("--help")){System.out.println("Usage: Main OUTPUT_DIRECTORY [case substring]\nCreates new exploratory evidence; refuses existing files. All families execute unless filtered.");return;}
        if(args.length<1||args.length>2)throw new IllegalArgumentException("Use --help");
        Capture.open(Path.of(args[0]),args.length==2?args[1]:"");
        try { GeometryCases.runAll();SceneCases.runAll();JointCases.runAll();InteractionCases.runAll();
            Class.forName("UpstreamCases").getMethod("run").invoke(null);
            UpstreamScaleCases.runAll();
        } finally {Capture.close();}
    }
}
