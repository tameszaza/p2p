import argparse
import asyncio
import json
import logging
import os

# aiortc imports
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription
)

# Enable debug-level logging for aiortc
logging.basicConfig(level=logging.DEBUG)

CHANNEL_LABEL = "p2p-data-channel"

# We'll track incoming file info here
incoming_files = {}


async def run_offer(pc, file_to_send):
    """
    Offer role:
    1. Create a data channel.
    2. Create an SDP offer, print it.
    3. Wait for remote SDP answer from the other peer.
    4. Stay alive for chat / file transfer.
    """
    # Create data channel for chat & file transfer
    channel = pc.createDataChannel(CHANNEL_LABEL)

    channel.on("open", lambda: on_channel_open(channel, file_to_send))
    channel.on("message", on_message_received)

    # Create and set local (offer) SDP
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    # Print the local SDP in JSON form
    print("=== Your OFFER (copy and send to the Answer peer) ===")
    print(json.dumps({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }))
    print("======================================================")

    # Wait for user to paste the ANSWER
    answer_str = input("Paste the ANSWER from the other peer and press Enter:\n").strip()
    try:
        answer_json = json.loads(answer_str)
        answer = RTCSessionDescription(
            sdp=answer_json["sdp"],
            type=answer_json["type"]
        )
        await pc.setRemoteDescription(answer)
    except Exception as e:
        print(f"Failed to parse answer: {e}")
        return

    # Keep the program alive
    await hold_connection()


async def run_answer(pc, file_to_send):
    """
    Answer role:
    1. Wait for the user to paste the remote SDP offer.
    2. Set it as remote description.
    3. Create an SDP answer, print it.
    4. Stay alive for chat / file transfer.
    """
    # Wait for the user to paste the OFFER
    offer_str = input("Paste the OFFER from the other peer and press Enter:\n").strip()

    try:
        offer_json = json.loads(offer_str)
        offer = RTCSessionDescription(
            sdp=offer_json["sdp"],
            type=offer_json["type"]
        )
        await pc.setRemoteDescription(offer)
    except Exception as e:
        print(f"Failed to parse offer: {e}")
        return

    @pc.on("datachannel")
    def on_datachannel(channel):
        print(f"DataChannel created by remote with label {channel.label}")
        channel.on("open", lambda: on_channel_open(channel, file_to_send))
        channel.on("message", on_message_received)

    # Create and set local (answer) SDP
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    print("=== Your ANSWER (copy and send to the Offer peer) ===")
    print(json.dumps({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }))
    print("=====================================================")

    # Keep the program alive
    await hold_connection()


def on_channel_open(channel, file_to_send):
    """
    Called when the data channel is open.
    - Send a test message
    - Start file transfer if file specified
    - Start chat prompt otherwise
    - Start a keep_alive task to try to keep NAT open
    """
    print("Data channel is open! You can start chatting or send a file.")

    # Send a quick test message
    channel.send("Test message from this peer.")

    # Start NAT keep-alive pings
    asyncio.ensure_future(keep_alive(channel))

    # If a file is specified, send it automatically
    if file_to_send and os.path.isfile(file_to_send):
        asyncio.ensure_future(send_file(channel, file_to_send))
    else:
        # Start chat
        asyncio.ensure_future(chat_prompt(channel))


async def keep_alive(channel, interval=5):
    """
    Periodically send a small message to keep the NAT mapping alive.
    Some NATs still may not respect this, so a TURN server is more reliable.
    """
    while True:
        await asyncio.sleep(interval)
        # If the channel is closed, stop
        if channel.readyState != "open":
            break
        try:
            channel.send("KEEP_ALIVE")
        except:
            break


async def chat_prompt(channel):
    """
    Continuously prompt the user for chat messages and send them.
    """
    while True:
        message = input("You: ").strip()
        if not message:
            continue
        if message.lower() == "bye":
            print("Ending chat. Goodbye!")
            channel.send("Peer has left the chat.")
            break
        channel.send(message)


async def send_file(channel, file_path):
    """
    Send a file across the data channel in small chunks.
    """
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    print(f"Sending file '{file_name}' ({file_size} bytes)...")

    # Let the remote side know we're sending a file
    meta_info = json.dumps({
        "file_name": file_name,
        "file_size": file_size,
        "type": "file_meta"
    })
    channel.send(meta_info)

    chunk_size = 16000
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            channel.send(chunk)
    print(f"File '{file_name}' sent successfully!")


def on_message_received(message):
    """
    Handles incoming messages (text or file chunks).
    """
    print(f"DEBUG: Message received: {message}")

    if isinstance(message, bytes):
        # File chunk
        handle_binary_message(message)
    else:
        # Possibly text or JSON
        try:
            data = json.loads(message)
            if data.get("type") == "file_meta":
                file_name = data["file_name"]
                file_size = data["file_size"]
                print(f"Incoming file: {file_name} ({file_size} bytes)")
                open_file_receiver(file_name, file_size)
            else:
                print("Peer:", data)
        except:
            # Normal text message
            print("Peer:", message)


def open_file_receiver(file_name, file_size):
    """
    Prepare to receive a file by opening a local file handle.
    """
    incoming_files[file_name] = {
        "file_name": file_name,
        "file_size": file_size,
        "received_bytes": 0,
        "handle": open(f"received_{file_name}", "wb")
    }
    print(f"Receiving file will be saved as 'received_{file_name}'")


def handle_binary_message(message):
    """
    Called when we receive a binary message (file chunk).
    """
    if len(incoming_files) == 1:
        file_info = next(iter(incoming_files.values()))
        file_info["handle"].write(message)
        file_info["received_bytes"] += len(message)

        if file_info["received_bytes"] >= file_info["file_size"]:
            file_info["handle"].close()
            print(f"File '{file_info['file_name']}' received successfully!")
            incoming_files.pop(file_info["file_name"])
    else:
        print("Warning: Received file chunk but no file metadata or multiple files in progress!")


async def hold_connection():
    """
    Keep the program running (for chat / file transfer).
    Press Ctrl+C to exit.
    """
    print("Connection established. Press Ctrl+C to stop.")
    while True:
        await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Simple P2P WebRTC with chat & file transfer")
    parser.add_argument("--role", choices=["offer", "answer"], required=True,
                        help="Role of this peer: 'offer' or 'answer'")
    parser.add_argument("--file", default=None,
                        help="Path to a file you want to send (optional)")
    args = parser.parse_args()

    # If NAT is restrictive, consider adding a TURN server:
    # Example:
    #
    # ice_servers = [
    #     RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
    #     RTCIceServer(
    #         urls=["turn:your-turn-server:3478"],
    #         username="username",
    #         credential="password"
    #     )
    # ]
    #
    # For now, let's just do STUN:
    ice_servers = [RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
    configuration = RTCConfiguration(iceServers=ice_servers)
    pc = RTCPeerConnection(configuration=configuration)

    # Avoid "no current event loop" warnings
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        if args.role == "offer":
            loop.run_until_complete(run_offer(pc, args.file))
        else:
            loop.run_until_complete(run_answer(pc, args.file))
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(pc.close())


if __name__ == "__main__":
    main()
