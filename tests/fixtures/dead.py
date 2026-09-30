def used():
    return 1


def unused_helper():
    return 2


@route("/x")
def handler():
    return 3


used()
