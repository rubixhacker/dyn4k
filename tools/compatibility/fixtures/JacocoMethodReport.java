import java.io.File;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import org.jacoco.core.analysis.Analyzer;
import org.jacoco.core.analysis.CoverageBuilder;
import org.jacoco.core.analysis.IClassCoverage;
import org.jacoco.core.analysis.IMethodCoverage;
import org.jacoco.core.tools.ExecFileLoader;

public final class JacocoMethodReport {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("usage: JacocoMethodReport EXEC JAR");
        }
        ExecFileLoader execution = new ExecFileLoader();
        execution.load(new File(args[0]));
        CoverageBuilder coverage = new CoverageBuilder();
        new Analyzer(execution.getExecutionDataStore(), coverage).analyzeAll(new File(args[1]));
        List<String> rows = new ArrayList<>();
        for (IClassCoverage type : coverage.getClasses()) {
            for (IMethodCoverage method : type.getMethods()) {
                rows.add(type.getName() + "\t" + method.getName() + "\t" + method.getDesc()
                        + "\t" + method.getInstructionCounter().getCoveredCount()
                        + "\t" + method.getInstructionCounter().getTotalCount());
            }
        }
        rows.sort(Comparator.naturalOrder());
        for (String row : rows) {
            System.out.println(row);
        }
    }
}
