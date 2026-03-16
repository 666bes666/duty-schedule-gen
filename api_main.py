import uvicorn

from duty_schedule.api import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("api_main:app", host="0.0.0.0", port=8000, reload=True)
