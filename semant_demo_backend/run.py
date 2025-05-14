from semant_demo.config import config

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("semant_demo.main:app", host="0.0.0.0", port=config.PORT, reload=True)
