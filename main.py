from fastapi import FastAPI, HTTPException, WebSocket, Request, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, MediaStreamTrack, RTCIceServer, RTCIceCandidate
import json
from dotenv import load_dotenv
import os
import uvicorn

load_dotenv(".env")
turn_server_username = os.getenv("TURN_SERVER_USERNAME")
turn_server_password = os.getenv("TURN_SERVER_PASSWORD")
turn_servers: list[RTCIceServer] = [
    RTCIceServer(
        urls=["turn:a.relay.metered.ca:80"],
        username=turn_server_username,
        credential=turn_server_password,
    ),
    RTCIceServer(
        urls=["turn:a.relay.metered.ca:80?transport=tcp"],
        username=turn_server_username,
        credential=turn_server_password,
    ),
    RTCIceServer(
        urls=["turn:a.relay.metered.ca:443"],
        username=turn_server_username,
        credential=turn_server_password,
    ),
    RTCIceServer(
        urls=["turn:a.relay.metered.ca:443?transport=tcp"],
        username=turn_server_username,
        credential=turn_server_username,
    ),
]

# Configure the RTCPeerConnection
configuration = RTCConfiguration(iceServers=turn_servers)

sender_stream: MediaStreamTrack | None = None
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("broadcaster.html", {"request": request})


@app.get("/mkbhd", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("viewer.html", {"request": request})


async def handle_media_stream(stream: MediaStreamTrack):
    global sender_stream
    # print(f"stream received and the kind is {stream.kind}")
    sender_stream = stream


def rtc_ice_candidate_arguments(candidate: dict):
    """Breaks the candidate into their individual components"""

    # Consider this SDP attribute line (a-line) which describes an ICE candidate:
    # a=candidate:4234997325 1 udp 2043278322 192.0.2.172 44323 typ host
    # The field "4234997325" is the foundation.
    # The next field on the a-line, "1", is the component ID. A value of "1" indicates RTP, which is recorded in the component property as "rtp". If this value were instead "2", the a-line would be describing an RTCP candidate, and component would be "rtcp".
    # The fifth field, "192.0.2.172" is the IP address in this candidate's a-line string.
    # The port number is found in the sixth field, which is "44323". In this case, the value of port will be 44323.
    # The priority is the number after the protocol, so it's the fourth field in the candidate string. In this example, the priority is 2043278322.
    # The third field, "udp", is the protocol type, indicating that the candidate would use the UDP transport protocol.

    # 'data': {'type': 'candidate', 'candidate': {'candidate': 'candidate:2062753407 1 udp 2122260223 172.21.144.1 57532 typ host generation 0 ufrag 4AtA network-id 2', 'sdpMid': '0', 'sdpMLineIndex': 0,
    # 'usernameFragment': '4AtA'}}}

    # candidate:2062753407 1 udp 2122260223 172.21.144.1 57532 typ host generation 0 ufrag 4AtA network-id 2
    sdp_a_line = candidate["candidate"]
    sdp_a_line = sdp_a_line.split(" ")
    foundation: str = sdp_a_line[0].split(":")[1]
    component: int = int(sdp_a_line[1])
    ip: str = sdp_a_line[4]
    port: int = int(sdp_a_line[5])
    priority: int = int(sdp_a_line[3])
    protocol: str = sdp_a_line[2]
    type: str = sdp_a_line[7]
    sdpMid = candidate["sdpMid"]
    sdpMLineIndex = candidate["sdpMLineIndex"]
    return {"component": component, "foundation": foundation, "ip": ip, "port": port, "priority": priority, "protocol": protocol, "type": type, "sdpMid": sdpMid, "sdpMLineIndex": sdpMLineIndex}


@app.websocket("/broadcaster")
async def broadcast(websocket: WebSocket):
    # every data that is sent to this endpoint has a type key
    # since the client is the one always sendign offer, i don't think i need to do this data[type] == offer since it is never answer
    global sender_stream
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            data = json.loads(data)
            # print("data received: ", data)
            data_content = data["data"]

            if data_content["type"] == "ready":
                send_data = {"data": {"type": "ready", "data": "nothing"}}
                await websocket.send_json(send_data)

            elif data_content["type"] == "offer":

                peer_connection = RTCPeerConnection(
                    configuration=configuration)
                peer_connection.on("track", handle_media_stream)

                offer = RTCSessionDescription(
                    sdp=data_content["sdp"], type=data_content["type"])
                await peer_connection.setRemoteDescription(offer)

                answer = await peer_connection.createAnswer()
                await peer_connection.setLocalDescription(answer)
                # print("answer about to be sent: ", answer)

                payload = {"data": {"type": peer_connection.localDescription.type,
                           "sdp": peer_connection.localDescription.sdp}}
                await websocket.send_json(payload)

                @peer_connection.on('icecandidate')
                async def handle_icecandidate(event):
                    if event.candidate is not None:
                        # print("this is ice candidate", event)
                        await websocket.send_json({'candidate': event.candidate})

            elif data_content["type"] == "candidate":
                await peer_connection.addIceCandidate(
                    RTCIceCandidate(**rtc_ice_candidate_arguments(data_content["candidate"])))
                print("candidate added")

    except WebSocketDisconnect:
        # del sender_stream
        print("broadcaster disconnected")


@app.websocket("/viewer")
async def person2(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            data = json.loads(data)
            # print("data received: ", data)
            data_content = data["data"]

            if data_content["type"] == "ready":
                send_data = {"data": {"type": "ready", "data": "nothing"}}
                await websocket.send_json(send_data)

            elif data_content["type"] == "offer":
                peer_connection = RTCPeerConnection(
                    configuration=configuration)

                offer = RTCSessionDescription(
                    sdp=data_content["sdp"], type=data_content["type"])
                await peer_connection.setRemoteDescription(offer)

                if not sender_stream:
                    raise HTTPException(
                        status_code=400, detail="No sender stream available")
                peer_connection.addTrack(sender_stream)

                answer = await peer_connection.createAnswer()
                await peer_connection.setLocalDescription(answer)

                print(f"sender stream is: {sender_stream}")
                # print("answer about to be sent: ", answer)
                payload = {"data": {"type": peer_connection.localDescription.type,
                           "sdp": peer_connection.localDescription.sdp}}
                await websocket.send_json(payload)

                @peer_connection.on('icecandidate')
                async def handle_icecandidate(event):
                    if event.candidate is not None:
                        # print("this is ice candidate", event)
                        await websocket.send_json({'candidate': event.candidate})

            elif data_content["type"] == "candidate":
                await peer_connection.addIceCandidate(
                    RTCIceCandidate(**rtc_ice_candidate_arguments(data_content["candidate"])))
                print("candidate added")

    except WebSocketDisconnect:
        print("a viewer disconnected")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0")
