How to Use

    Install dependencies:

pip install aiortc

Run the script in offer mode on one machine:

python p2p.py --role offer --file /path/to/yourfile.bin

    This will generate and print an offer (in JSON).
    Copy the entire JSON block and keep the program running.

Run the script in answer mode on the other machine:

    python p2p.py --role answer

        It will ask for the offer. Paste the JSON block you got from the other peer.
        It will then generate and print an answer (in JSON).
        Copy that JSON and paste it into the offer peer’s prompt.

    After the exchange, both sides should display “Data channel is open!”. Chat is possible, and file transfer will start automatically if a file was specified by the --file argument on the offering side (or on the answering side if you want to do it in reverse).

    When a file arrives, it’s saved under the name received_<filename> by default in the current directory.

Explanation

    aiortc library handles the WebRTC negotiation for us. We create a RTCPeerConnection and either:
        In offer mode, we call createDataChannel() to initiate a data channel, then call createOffer(), and set it locally (setLocalDescription()).
        In answer mode, we wait for the user to paste the offer, then set it as remote description. We create an answer and set it locally.

    Signaling: Since we aren’t using a separate signaling server, we do a manual paste of the SDP objects (offer and answer). This is purely so each peer knows how to connect (ICE candidates, connection parameters, etc.).

    Data channel is used for both text chat and file transfer. We handle:
        Text: If the channel receives a str, we try to see if it’s JSON or plain text.
        File: If the channel receives bytes, we treat it as a file chunk. We also have a small “metadata” JSON that alerts the receiving side about the file name and size.

    File chunking: We send the file in small chunks so we can handle large files without blocking. On the receiving side, we write chunks to a local file until we reach the total size.

This is only a basic demonstration. For real-world scenarios, you’d add:

    Automatic STUN/TURN configuration (aiortc can use custom STUN/TURN servers).
    Better user interface (maybe a terminal UI or a small GUI).
    Proper error handling.
    Multiple files or multi-channel support.

But with this script, you have a working example of a truly peer-to-peer connection with text chat and file transfer using WebRTC without requiring a dedicated server for the data channel itself!
In the provided script, once the data channel is open, you can chat by entering messages directly into the terminal where the program is running.

Here’s a step-by-step guide to start chatting:

### 1. **Run the script on both peers**

- One peer runs the script in **offer mode**:
  ```bash
  python p2p.py --role offer
  ```

- The other peer runs the script in **answer mode**:
  ```bash
  python p2p.py --role answer
  ```

### 2. **Exchange the SDP**

- The peer in **offer mode** will generate an offer (a JSON block) and print it to the terminal.
- Copy the offer and paste it into the terminal of the peer running in **answer mode**.
- The peer in **answer mode** will then generate an answer (another JSON block) and print it.
- Copy the answer and paste it into the terminal of the **offer peer**.

### 3. **Start chatting**

Once the connection is established and the data channel opens, you can start chatting:

- On both peers, you’ll see this message in the terminal:
  ```
  Data channel is open! You can start chatting or send a file.
  ```

- To send a message:
  - Simply type your message in the terminal and press **Enter**.
  - This will send the message to the other peer.

- On the receiving side, the message will appear in their terminal, prefixed with `Peer:`.

### 4. **Example**

- Peer 1 sends:
  ```
  Hello, how are you?
  ```

- Peer 2 receives:
  ```
  Peer: Hello, how are you?
  ```

- Peer 2 replies:
  ```
  I'm good, thank you! How about you?
  ```

- Peer 1 receives:
  ```
  Peer: I'm good, thank you! How about you?
  ```

---

### Sending a File

- If a file is specified using the `--file` argument when running the script (e.g., `--file myfile.txt`), the file will automatically be sent over the data channel once it's open.

- The receiving peer will see a message indicating the file transfer, and the file will be saved as `received_<filename>` in their current directory.

---

This implementation is a basic proof of concept. If you want a more polished chat experience, consider enhancing it with:

- A terminal-based UI (e.g., using the `curses` library).
- Logging chat messages to a file.
- Handling simultaneous chat and file transfer more smoothly.