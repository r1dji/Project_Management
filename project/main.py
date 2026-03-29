import uvicorn

if __name__ == '__main__':
    uvicorn.run('server:app', reload=True, host='0.0.0.0', port=8000)
    try:
        print("promena")
    except:
        print("error")
    #promena 1
    #promena posle dodatih testova