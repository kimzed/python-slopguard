def tangled(a, b, c, d, e, f):
    total = 0
    if a:
        if b:
            if c:
                if d:
                    total += 1
    for item in e:
        if item > 0 and f:
            total += item
        elif item < 0 or not f:
            total -= item
        else:
            while total > 100:
                total //= 2
    return total
