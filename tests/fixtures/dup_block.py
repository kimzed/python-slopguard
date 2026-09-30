def process(records, threshold):
    result = []
    for record in records:
        if record.get("status") == "active" and record.get("score", 0) > threshold:
            name = record["name"].strip().lower()
            tags = [tag.upper() for tag in record.get("tags", []) if tag]
            result.append({"name": name, "tags": tags, "score": record["score"]})
    result.sort(key=lambda item: item["score"], reverse=True)
    return result
