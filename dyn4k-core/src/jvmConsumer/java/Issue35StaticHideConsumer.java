import org.dyn4j.collision.AbstractCollisionItem;
import org.dyn4j.collision.CollisionBody;
import org.dyn4j.collision.CollisionItem;
import org.dyn4j.collision.Fixture;

final class Issue35StaticHideConsumer extends AbstractCollisionItem<CollisionBody<Fixture>, Fixture> {
    @Override public CollisionBody<Fixture> getBody() { return null; }
    @Override public Fixture getFixture() { return null; }
    @Override public CollisionItem<CollisionBody<Fixture>, Fixture> copy() { return this; }
    public static int getHashCode(CollisionBody<?> body, Fixture fixture) { return 0; }
    public static boolean equals(CollisionItem<?, ?> item, Object other) { return false; }
}
