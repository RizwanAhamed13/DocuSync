from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def root():
    return {"app": "quad-python-example", "stack": "python"}
