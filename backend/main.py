# pyrefly: ignore [missing-import]
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
from agent import run_agent

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Agent Backend is running"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "command":
                user_instruction = message.get("content")
                
                # Callback to send updates back to the UI
                loop = asyncio.get_running_loop()

                def send_update(status_text: str):
                    asyncio.run_coroutine_threadsafe(
                        websocket.send_text(json.dumps({"type": "update", "content": status_text})),
                        loop,
                    )
                
                await websocket.send_text(json.dumps({"type": "update", "content": f"Received command: {user_instruction}"}))
                
                # Run the agent (this should ideally be non-blocking in production, but okay for demo)
                try:
                    final_result = await run_agent(user_instruction, send_update)
                    await websocket.send_text(json.dumps({"type": "result", "content": final_result}))
                except Exception as e:
                    await websocket.send_text(json.dumps({"type": "error", "content": str(e)}))
                    
    except WebSocketDisconnect:
        print("Client disconnected")

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
