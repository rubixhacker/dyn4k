import java.io.InputStream;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class ClassfileDispatchReport {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: ClassfileDispatchReport JAR");
        }
        List<String> rows = new ArrayList<>();
        try (JarFile jar = new JarFile(args[0])) {
            for (JarEntry entry : java.util.Collections.list(jar.entries())) {
                if (!entry.getName().endsWith(".class")) {
                    continue;
                }
                try (InputStream stream = jar.getInputStream(entry)) {
                    ClassReader reader = new ClassReader(stream);
                    reader.accept(new ClassVisitor(Opcodes.ASM9) {
                        private String owner;

                        @Override
                        public void visit(int version, int access, String name, String signature,
                                          String superName, String[] interfaces) {
                            owner = name;
                            rows.add("C\t" + name + "\t" + access + "\t"
                                    + (superName == null ? "" : superName) + "\t"
                                    + String.join(",", interfaces));
                        }

                        @Override
                        public MethodVisitor visitMethod(int access, String name, String descriptor,
                                                         String signature, String[] exceptions) {
                            rows.add("M\t" + owner + "\t" + name + "\t" + descriptor
                                    + "\t" + access);
                            return new MethodVisitor(Opcodes.ASM9) {
                                private final StringBuilder opcodes = new StringBuilder();

                                private void opcode(int value) {
                                    if (opcodes.length() > 0) {
                                        opcodes.append(',');
                                    }
                                    opcodes.append(value);
                                }

                                @Override
                                public void visitInsn(int opcode) {
                                    opcode(opcode);
                                }

                                @Override
                                public void visitVarInsn(int opcode, int variable) {
                                    opcode(opcode);
                                }

                                @Override
                                public void visitIntInsn(int opcode, int operand) {
                                    opcode(opcode);
                                }

                                @Override
                                public void visitTypeInsn(int opcode, String type) {
                                    opcode(opcode);
                                }

                                @Override
                                public void visitFieldInsn(int opcode, String targetOwner,
                                                           String targetName, String targetDescriptor) {
                                    opcode(opcode);
                                }

                                @Override
                                public void visitMethodInsn(int opcode, String targetOwner,
                                                            String targetName, String targetDescriptor,
                                                            boolean isInterface) {
                                    opcode(opcode);
                                    rows.add("I\t" + owner + "\t" + name + "\t" + descriptor
                                            + "\t" + opcode + "\t" + targetOwner + "\t"
                                            + targetName + "\t" + targetDescriptor);
                                }

                                @Override
                                public void visitInvokeDynamicInsn(String targetName,
                                                                   String targetDescriptor,
                                                                   Handle bootstrap, Object... arguments) {
                                    opcode(Opcodes.INVOKEDYNAMIC);
                                }

                                @Override
                                public void visitJumpInsn(int opcode, Label label) {
                                    opcode(opcode);
                                }

                                @Override
                                public void visitLdcInsn(Object value) {
                                    opcode(Opcodes.LDC);
                                }

                                @Override
                                public void visitIincInsn(int variable, int increment) {
                                    opcode(Opcodes.IINC);
                                }

                                @Override
                                public void visitTableSwitchInsn(int minimum, int maximum,
                                                                 Label defaultLabel, Label... labels) {
                                    opcode(Opcodes.TABLESWITCH);
                                }

                                @Override
                                public void visitLookupSwitchInsn(Label defaultLabel, int[] keys,
                                                                  Label[] labels) {
                                    opcode(Opcodes.LOOKUPSWITCH);
                                }

                                @Override
                                public void visitMultiANewArrayInsn(String type, int dimensions) {
                                    opcode(Opcodes.MULTIANEWARRAY);
                                }

                                @Override
                                public void visitTryCatchBlock(Label start, Label end,
                                                               Label handler, String type) {
                                    opcode(-1);
                                }

                                @Override
                                public void visitEnd() {
                                    rows.add("O\t" + owner + "\t" + name + "\t" + descriptor
                                            + "\t" + opcodes);
                                }
                            };
                        }
                    }, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
                }
            }
        }
        rows.sort(Comparator.naturalOrder());
        for (String row : rows) {
            System.out.println(row);
        }
    }
}
