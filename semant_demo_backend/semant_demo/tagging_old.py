from semant_demo import schemas

def tag_and_store(tagReq: schemas.TagTemplate, taskId: str):
    try:
        task_status[task_id] = "Running"
        
        # load from weaviate
        # process using llm
        # store result in the weaviate db
        with open("log.txt", mode="w") as log_file:
            log_file.write(f"Starting task with data: {str(tagReq)}")
            import time
            time.sleep(100)
            log_file.write(f"Task finished")
        task_status[task_id] = "COMPLETED"
    except Exception as e:
        task_status[task_id] = f"FAILED: {str(e)}"

if __name__ == "__main__":
    result = tag_and_store.delay({
        "tag": "test",
        "description": "test",
        "examples": ["test1"]
    })
    print(f"Task ID: {result.id}")