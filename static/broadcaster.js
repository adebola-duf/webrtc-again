// const id = Date.now()
let pc;
let localStreamElement = document.getElementById('localStream');
let remoteStreamElement = document.getElementById('remoteStream');
let lecturer = true
socket = new WebSocket(`wss://${window.location.hostname}/broadcaster`);
console.log("This is ws: ", socket)

var peerConfiguration = {};

const sendData = (data) => {
    console.log("sending data");
    const jsonData = JSON.stringify({"data": data});
    console.log(jsonData);  
    socket.send(jsonData);
};

const startConnection = () => {
    
    navigator.mediaDevices
        .getDisplayMedia({
            audio: true,
            video: {
                height: 350,
                width: 350,
            },
        })
        .then((stream) => {
            localStreamElement.srcObject = stream;
            data = {type: "ready", data: "nothing"};
            sendData(data);
        })
        .catch((error) => {
            console.error("Stream not found: ", error);
        });
        
    }


const onIceCandidate = (event) => {
    if (event.candidate) {
        sendData({
            type: "candidate",
            candidate: event.candidate,
        });
    }
};

const onTrack = (event) => {
    remoteStreamElement.srcObject = event.streams[0];
};


const createPeerConnection = () => {
    try {
        pc = new RTCPeerConnection(peerConfiguration);
        // pc.onicecandidate = onIceCandidate;
        // pc.ontrack = onTrack;

        const localStream = localStreamElement.srcObject;
        localStream.getTracks().forEach((track) => {
            pc.addTrack(track, localStream);
        });

        console.log("PeerConnection created");
    } catch (error) {
        console.error("PeerConnection failed: ", error);
    }
};

const setAndSendLocalDescription = (sessionDescription) => {
    pc.setLocalDescription(sessionDescription)
        .then(() => {
            console.log("Local description set");
            sendData(sessionDescription);
        })
        .catch((error) => {
            console.error("Error setting local description: ", error);
        });
};


const sendOffer = () => {
    console.log("Sending offer");
    pc.createOffer()
        .then(setAndSendLocalDescription)
        .catch((error) => {
            console.error("Send offer failed: ", error);
        });
};

const signalingDataHandler = (data) => {
    if (data.type === "answer") {
        pc.setRemoteDescription(new RTCSessionDescription(data))
            .catch((error) => {
                console.error("Error setting remote description for answer: ", error);
            });
    } 
    else if (data.type === "candidate") {
        pc.addIceCandidate(new RTCIceCandidate(data.candidate))
            .catch((error) => {
                console.error("Error adding ICE candidate: ", error);
            });
    } 
    else if(data.type === "ready"){
        createPeerConnection();
        sendOffer();
    }
    else {
        console.log("Unknown Data");
    }
};

socket.onmessage = function(event) {
    var message = event.data
    
    try{
        var jsonMessage = JSON.parse(message);
        console.log("Data received", jsonMessage.data)
        signalingDataHandler(jsonMessage.data)
    

    }catch(e){
        console.log("An error occured in parsing the json", e);
    }
}

window.addEventListener("beforeunload", () => {
    if (pc) {
        pc.close();
    }
});

// Start the connection when the page loads
socket.onopen = function () {
    console.log("Websocket connected!");
    startConnection();
  };