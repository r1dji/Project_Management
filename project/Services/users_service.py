from Database.models import User


def get_user_by_username(db, username):
    return db.query(User).filter(User.username == username).first()


def insert_user(db, username, password):
    new_user = User(
        username=username,
        password=password
    )
    try:
        db.add(new_user)
        db.commit()
        return True
    except Exception as e:
        db.rollbck()
        print(e)
        return False
