
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("cmd.server:app", host="0.0.0.0", port=3000, reload=True)
