/*
 * Copyright (c) 2010-2021 William Bittle  http://www.dyn4j.org/
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without modification, are permitted
 * provided that the following conditions are met:
 *
 *   * Redistributions of source code must retain the above copyright notice, this list of conditions
 *     and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above copyright notice, this list of conditions
 *     and the following disclaimer in the documentation and/or other materials provided with the
 *     distribution.
 *   * Neither the name of the copyright holder nor the names of its contributors may be used to endorse or
 *     promote products derived from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
 * FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
 * IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
 * OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
import org.dyn4j.dynamics.*; import org.dyn4j.geometry.*; import org.dyn4j.world.World; import org.dyn4j.dynamics.joint.*; import junit.framework.TestCase;
public final class UpstreamScaleCases {
public static void runAll() { for(double scale:new double[]{0.01,1,100}) for(double[] o:new double[][]{{0,0},{1000,1000},{-1000,1000},{1000000,-1000000},{-1000000,1000000}}) {fixedDistance(scale,o[0],o[1]); motorWithAndWithoutLimits(scale,o[0],o[1]);}}
public static void fixedDistance(double scale,double ox,double oy) {
if (!Capture.accepts("U-scale-fixedDistance-"+scale+"-"+ox+"-"+oy)) return;

		World<Body> w = new World<Body>(); SceneCases.scaleWorld(w,scale);
		// take gravity out the picture
		w.setGravity(World.ZERO_GRAVITY);

		// take friction and damping out of the picture

		Body g = new Body();
		BodyFixture gf = g.addFixture(Geometry.createRectangle(10.0*scale, 0.5*scale));
		gf.setRestitutionVelocity(gf.getRestitutionVelocity()*scale); gf.setFriction(0.0);
		g.setMass(MassType.INFINITE);
		g.setLinearDamping(0.0);
		g.setAngularDamping(0.0);
		g.translate(ox,oy); w.addBody(g);

		Body b = new Body();
		BodyFixture bf = b.addFixture(Geometry.createCircle(0.5*scale));
		bf.setRestitutionVelocity(bf.getRestitutionVelocity()*scale); bf.setFriction(0.0);
		b.setMass(MassType.NORMAL);
		b.translate(ox, oy+2.0*scale);
		b.setLinearDamping(0.0);
		b.setAngularDamping(0.0);
		w.addBody(b);

		DistanceJoint<Body> dj = new DistanceJoint<Body>(g, b, g.getWorldCenter(), b.getWorldCenter());

		dj.setRestDistance(10.0*scale);
		w.addJoint(dj);

		Vector2 v1 = g.getWorldCenter();
		Vector2 v2 = b.getWorldCenter();
		double exactInitialDistance = v1.distance(v2)/scale;
        String exactInitialStatus = "PASS";
        try { TestCase.assertEquals(2.0, exactInitialDistance); }
        catch (junit.framework.AssertionFailedError mismatch) { exactInitialStatus = "FAIL"; }
        Capture.record("U-scale-fixedDistance-"+scale+"-"+ox+"-"+oy, "original-exact-initial-assertion", 2.0, exactInitialDistance, exactInitialStatus);

		// the way the distance joint is currently working is that it will immediately try to solve
		// it to be the correct distance apart, but the position solver is bound by the default
		// correction factor, which is 0.2m. The world is also specified to run 10 position solving
		// iterations as well so this accounts for +2m difference each iteration, so after 4 iterations
		// we should be at 10m (we'll set these defaults below just in case they change in the future)
		w.getSettings().setMaximumLinearCorrection(0.2*scale);
		w.getSettings().setPositionConstraintSolverIterations(10);
		Capture.run("U-scale-fixedDistance-"+scale+"-"+ox+"-"+oy,w,4,1.0/60.0,scale,ox,oy,n -> {});

		double invdt = w.getTimeStep().getInverseDeltaTime();

		v1 = g.getWorldCenter();
		v2 = b.getWorldCenter();
		TestCase.assertEquals(v1.distance(v2)/scale, dj.getRestDistance()/scale, 1e-5);
		// always zero
		TestCase.assertEquals(0.0, dj.getReactionTorque(invdt)/(scale*scale*scale*scale));
		// position correction doesn't store impulses
		TestCase.assertEquals(0.0, dj.getReactionForce(invdt).x/(scale*scale*scale), 1e-3);
		TestCase.assertEquals(0.0, dj.getReactionForce(invdt).y/(scale*scale*scale), 1e-3);
		TestCase.assertEquals(0.0, dj.getSpringForce(invdt)/(scale*scale*scale), 1e-3);
}
public static void motorWithAndWithoutLimits(double scale,double ox,double oy) {
if (!Capture.accepts("U-scale-motorWithAndWithoutLimits-"+scale+"-"+ox+"-"+oy)) return;

		World<Body> w = new World<Body>(); SceneCases.scaleWorld(w,scale);
		// take gravity out the picture
		w.setGravity(World.ZERO_GRAVITY);
		w.getSettings().setAngularTolerance(0.0);

		// take friction and damping out of the picture

		Body g = new Body();
		BodyFixture gf = g.addFixture(Geometry.createRectangle(10.0*scale, 0.5*scale));
		gf.setRestitutionVelocity(gf.getRestitutionVelocity()*scale); gf.setFriction(0.0);
		g.setMass(MassType.INFINITE);
		g.setLinearDamping(0.0);
		g.setAngularDamping(0.0);
		g.translate(ox,oy); w.addBody(g);

		Body b = new Body();
		BodyFixture bf = b.addFixture(Geometry.createCircle(0.5*scale));
		bf.setRestitutionVelocity(bf.getRestitutionVelocity()*scale); bf.setFriction(0.0);
		b.setMass(MassType.NORMAL);
		b.translate(ox, oy+2.0*scale);
		b.setLinearDamping(0.0);
		b.setAngularDamping(0.0);
		w.addBody(b);

		RevoluteJoint<Body> rj = new RevoluteJoint<Body>(g, b, b.getWorldCenter());

		// NOTE: that I've set the rest distance to more than the limits
		rj.setMaximumMotorTorque(1000*scale*scale*scale*scale);
		rj.setMaximumMotorTorqueEnabled(true);
		rj.setMotorSpeed(Math.toRadians(20));
		rj.setMotorEnabled(true);
		w.addJoint(rj);

		double invdt = w.getTimeStep().getInverseDeltaTime();

		TestCase.assertEquals(0.0, rj.getAngularTranslation());
		TestCase.assertEquals(0.0000, rj.getAngularSpeed(), 1e-5);
		TestCase.assertEquals(0.0, rj.getMotorTorque(invdt));

		Capture.run("U-scale-motorWithAndWithoutLimits-"+scale+"-"+ox+"-"+oy,w,1,1.0/60.0,scale,ox,oy,n -> {});

		// since the bodies are already 2.0 units apparent, nothing should happen
		TestCase.assertEquals(0.00581, b.getTransform().getRotationAngle(), 1e-5);
		TestCase.assertEquals(0.34906, b.getAngularVelocity(), 1e-5);
		TestCase.assertEquals(Math.toRadians(20) / 60.0, rj.getAngularTranslation(), 1e-5);
		TestCase.assertEquals(Math.toRadians(20), rj.getAngularSpeed(), 1e-5);
		TestCase.assertEquals(2.05616, rj.getReactionTorque(invdt)/(scale*scale*scale*scale), 1e-3);

		rj.setLimitsEnabled(-Math.toRadians(5), Math.toRadians(5));
		Capture.run("U-scale-motorWithAndWithoutLimits-"+scale+"-"+ox+"-"+oy,w,30,1.0/60.0,scale,ox,oy,n -> {});

		// the bodies should be placed at the upper limit
		TestCase.assertEquals(0.08726, b.getTransform().getRotationAngle(), 1e-5);
		TestCase.assertEquals(0.00000, b.getAngularVelocity(), 1e-5);
		TestCase.assertEquals(0.00000, rj.getAngularSpeed(), 1e-3);
		TestCase.assertEquals(0.08726, rj.getAngularTranslation(), 1e-3);
		TestCase.assertEquals(0.000, rj.getReactionTorque(invdt)/(scale*scale*scale*scale), 1e-3);

		rj.setMotorSpeed(-Math.toRadians(20));
		Capture.run("U-scale-motorWithAndWithoutLimits-"+scale+"-"+ox+"-"+oy,w,1,1.0/60.0,scale,ox,oy,n -> {});

		// the bodies should be placed at the upper limit
		TestCase.assertEquals(0.08144, b.getTransform().getRotationAngle(), 1e-5);
		TestCase.assertEquals(-0.34906, b.getAngularVelocity(), 1e-5);
		TestCase.assertEquals(-0.34906, rj.getAngularSpeed(), 1e-3);
		TestCase.assertEquals(0.08144, rj.getAngularTranslation(), 1e-3);
		TestCase.assertEquals(-2.05616, rj.getReactionTorque(invdt)/(scale*scale*scale*scale), 1e-3);

		Capture.run("U-scale-motorWithAndWithoutLimits-"+scale+"-"+ox+"-"+oy,w,60,1.0/60.0,scale,ox,oy,n -> {});

		// the bodies should be placed at the lower limit
		TestCase.assertEquals(-0.08726, b.getTransform().getRotationAngle(), 1e-5);
		TestCase.assertEquals(0.00000, b.getAngularVelocity(), 1e-5);
		TestCase.assertEquals(0.00000, rj.getAngularSpeed(), 1e-3);
		TestCase.assertEquals(-0.08726, rj.getAngularTranslation(), 1e-3);
		TestCase.assertEquals(0.000, rj.getReactionTorque(invdt)/(scale*scale*scale*scale), 1e-3);
}
}
