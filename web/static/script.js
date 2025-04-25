let audioContext;
let processor;
let input;
let backendAudioElements = [];
let backendAudioQueue = [];
let isPlayingBackendAudio = false;
let socket;
// const recordingsBox = document.getElementById('recordingsBox');
// const backendRecordingsBox = document.getElementById('backendRecordingsBox');
const chatBox = document.getElementById('chatBox');
// const messageBox = document.getElementById('messageBox');
const logBox = document.getElementById('logBox');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');

// 新增：阻止状态标志
let isBlocked = false;

class MessageType {
    static SYSTEM = 'system';
    static USER = 'user';
    static BOT = 'bot';
}


// 添加事件
document.addEventListener("DOMContentLoaded", function () {
    console.log("页面 DOM 加载完成");
    initializeWebSocket(); // 初始化 WebSocket
});
sendBtn.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    //
    const msgObj = {
        id: generateMessageId(),
        content: message,
        type: MessageType.USER,
        timestamp: new Date().toISOString()
    };

    addMessage(message, MessageType.USER, msgObj.id);
    socket.send(JSON.stringify(msgObj));
    messageInput.value = '';
}

// 初始化 WebSocket
function initializeWebSocket() {
    const wsUrl = 'ws://localhost:8888/ws';   //填写运行server的地址
    socket = new WebSocket(wsUrl);

    socket.binaryType = 'arraybuffer';

    socket.onopen = () => {
        console.log('WebSocket 连接已打开');
        addLog("WebSocket 连接已打开")
    };

    socket.onmessage = (event) => {

        if (typeof event.data === 'string') {
            // const message = event.data;
            const resp = JSON.parse(event.data)
            const msgType = resp.msgType
            const messageId = resp.messageId
            const message = resp.data
            if (msgType === 'system') {
                if (message === '$clear$') {
                    if (isBlocked) {
                        console.log('已在阻止状态，忽略$clear$消息');
                        return;
                    }

                    // 设置阻止状态
                    isBlocked = true;

                    // 停止并重置所有正在播放的后端音频
                    backendAudioElements.forEach(audio => {
                        audio.pause();
                        audio.currentTime = 0; // 重置播放时间
                        audio.onended = null;   // 移除结束事件监听器
                        audio.onerror = null;   // 移除错误事件监听器
                    });

                    // 清空后端音频元素数组
                    backendAudioElements = [];

                    // 清空后端音频队列
                    backendAudioQueue = [];

                    // 停止后端音频播放
                    isPlayingBackendAudio = false;

                    // 禁用播放后端录音按钮
                    // document.getElementById('playBackendRecordingsButton').disabled = true;

                    addLog("音频队列已清空,停止讲话")
                    // 设置0.5秒的阻止时间
                    setTimeout(() => {
                        isBlocked = false;
                        addLog('阻止状态已解除，可以继续接收音频。')
                    }, 500);
                    return;
                } else {
                    addLog(message)
                    return;
                }
            }


            console.log('收到消息:', message);
            const existEle = document.querySelector(`[data-message-id="${messageId}"]`);
            if (existEle) {
                // 如果已有相同 messageId 的消息，直接追加文本
                const messageText = document.createTextNode(message);
                existEle.appendChild(messageText);
            } else {
                addMessage(message, msgType, messageId);
                // const fragment = document.createDocumentFragment();
                // const timestamp = new Date().toLocaleTimeString();
                //
                // const roleDiv = document.createElement('div');
                // const timeTag = document.createElement('span')
                // timeTag.innerText = timestamp;
                // roleDiv.appendChild(timeTag);
                //
                // const messageElement = document.createElement('div');
                // messageElement.setAttribute("data-message-id", messageId);
                //
                // // messageElement.innerHTML = `<strong>${timestamp}:</strong> `;
                // const messageText = document.createTextNode(message);
                // messageElement.appendChild(messageText);
                //
                // // 添加不同的类来标识系统和用户消息
                // if (msgType === MessageType.BOT) {
                //     roleDiv.classList.add('assistant-role')
                //     roleDiv.innerText = 'Assistant';
                //     messageElement.classList.add('assistant-message');
                // } else if (msgType === MessageType.USER) {
                //     roleDiv.classList.add('user-role')
                //     messageElement.classList.add('user-message');
                //     roleDiv.innerText = 'User';
                // }
                // fragment.appendChild(messageElement);
                //
                // messageBox.appendChild(roleDiv)
                // messageBox.appendChild(fragment);


            }

            // chatBox.appendChild(messageBox)

            // chatBox.scrollTop = chatBox.scrollHeight;
        } else {
            // 处理音频数据
            console.log('处理音频数据...')

            // 如果处于阻止状态，忽略新的音频数据
            if (isBlocked) {
                console.log('处于阻止状态，忽略新的音频数据');
                return;
            }

            const arrayBuffer = event.data;
            const blob = new Blob([arrayBuffer], {type: 'audio/wav'});
            const audioUrl = URL.createObjectURL(blob);
            const audioElement = document.createElement('audio');
            audioElement.src = audioUrl;
            backendAudioElements.push(audioElement);

            const listItem = document.createElement('div');
            listItem.classList.add('audio-item');
            listItem.appendChild(audioElement);
            // backendRecordingsBox.appendChild(listItem);

            // document.getElementById('playBackendRecordingsButton').disabled = false;

            backendAudioQueue.push(audioElement);
            playBackendAudioQueue();

            chatBox.scrollTop = chatBox.scrollHeight;
        }
    };

    socket.onerror = (error) => {
        console.error('WebSocket 错误:', error);
        addLog("WebSocket 错误，请检查连接")
    };

    socket.onclose = () => {
        console.log('WebSocket 连接已关闭');
        addLog("WebSocket 连接已关闭")
    };
}

function addLog(message) {
    const fragment = document.createDocumentFragment();
    const messageElement = document.createElement('div');
    messageElement.innerText = message;
    messageElement.classList.add('system-message');
    fragment.appendChild(messageElement);
    logBox.appendChild(fragment);
    logBox.scrollTop = logBox.scrollHeight;
}

function addMessage(text, msgType, messageId) {
    if (!text) {
        return;
    }
    if (!messageId) {
        messageId = generateMessageId();
    }
    const fragment = document.createDocumentFragment();

    const messageContainer = document.createElement('div')
    messageContainer.className = 'message_container'
    const messageDiv = document.createElement('div')
    messageDiv.className = `message_content_${msgType}`
    const timestamp = new Date().toLocaleTimeString()


    // head_portrait
    const headPortrait = document.createElement('div')
    headPortrait.className = `head_portrait_${msgType}`
    if (MessageType.BOT === msgType) {
        headPortrait.innerHTML = '<img src="../static/img/iron_man.jpg" alt="头像" style="width: 30px; height: 30px;">'
    } else if (MessageType.USER === msgType) {
        headPortrait.innerHTML = '<img src="../static/img/spider_man2.png" alt="头像" style="width: 30px; height: 30px;">'
    }

    // role info
    const roleDiv = document.createElement('div')
    roleDiv.className = `role_info_${msgType}`
    const span = document.createElement('span')
    span.innerText = timestamp
    roleDiv.innerText = msgType
    roleDiv.innerHTML = `<strong>${msgType} </strong>`;
    roleDiv.appendChild(span)


    // 消息体
    const content = document.createElement('div');
    content.className = `message_${msgType}`;
    content.setAttribute('data-message-id', messageId);
    content.innerText = text

    messageDiv.appendChild(roleDiv)
    messageDiv.appendChild(content)
    messageContainer.appendChild(headPortrait);
    messageContainer.appendChild(messageDiv);
    fragment.appendChild(messageContainer)
    chatBox.appendChild(fragment);
    scrollToBottom();
}

function generateMessageId() {
    // const uuid = crypto.randomUUID();
    return crypto.randomUUID();
}

function scrollToBottom() {
    chatBox.scrollTop = chatBox.scrollHeight;
}

document.getElementById("startButton").onclick = async () => {
    // initializeWebSocket();

    try {
        const stream = await navigator.mediaDevices.getUserMedia({audio: true});   //
        audioContext = new (window.AudioContext || window.webkitAudioContext)({sampleRate: 16000});
        input = audioContext.createMediaStreamSource(stream);

        // 使用 ScriptProcessorNode 捕获音频数据
        const bufferSize = 4096;
        processor = audioContext.createScriptProcessor(bufferSize, 1, 1);

        input.connect(processor);
        processor.connect(audioContext.destination);

        processor.onaudioprocess = (e) => {
            const channelData = e.inputBuffer.getChannelData(0);
            // 转换 Float32Array 到 Int16Array (PCM 16位)
            const pcmData = floatTo16BitPCM(channelData);
            // 发送 PCM 数据到后端
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(pcmData.buffer);
                console.log('PCM 数据已发送到后端');
            } else {
                console.error('WebSocket 未连接');
                addLog("WebSocket 未连接，无法发送音频数据")
            }

            // 可选：保存录音（如果需要）
            // saveRecording(channelData);
        };

        document.getElementById("stopButton").disabled = false;
        document.getElementById("startButton").disabled = true;
        addLog("开始语音输入...")
        addLog("等待说话...")
    } catch (err) {
        console.error('获取音频权限失败:', err);
        addLog("获取音频权限失败，请检查设备设置")
    }
};

document.getElementById("stopButton").onclick = () => {
    if (processor) {
        processor.disconnect();
        processor.onaudioprocess = null;
        processor = null;
    }
    if (input) {
        input.disconnect();
        input = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }

    // 关闭 WebSocket 连接
    // if (socket && socket.readyState === WebSocket.OPEN) {
    //     socket.close();
    // }

    document.getElementById("startButton").disabled = false;
    document.getElementById("stopButton").disabled = true;

    addLog("停止语音交互")
};

// 转换 Float32Array 到 Int16Array
function floatTo16BitPCM(float32Array) {
    const int16Array = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
        let s = Math.max(-1, Math.min(1, float32Array[i]));
        int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return int16Array;
}

let recordedAudioBuffers = [];

function saveRecording(channelData) {
    recordedAudioBuffers.push(new Float32Array(channelData));

    // 将录音转换为 Blob 并显示
    const blob = new Blob(recordedAudioBuffers.map(buffer => {
        return new Blob([bufferToWave(buffer, audioContext.sampleRate)], {type: 'audio/wav'});
    }), {type: 'audio/wav'});

    const audioUrl = URL.createObjectURL(blob);
    const audioElement = document.createElement('audio');
    audioElement.controls = true;
    audioElement.src = audioUrl;
    // recordingsBox.appendChild(audioElement);

    document.getElementById('playRecordingsButton').disabled = false;
}

// Helper 函数将 Float32Array 转换为 WAV 格式（可选）
function bufferToWave(abuffer, sampleRate) {
    const buffer = abuffer;
    const numOfChan = 1;
    const length = buffer.length * 2 + 44;
    const bufferArray = new ArrayBuffer(length);
    const view = new DataView(bufferArray);

    /* RIFF identifier */
    writeString(view, 0, 'RIFF');
    /* file length */
    view.setUint32(4, 36 + buffer.length * 2, true);
    /* RIFF type */
    writeString(view, 8, 'WAVE');
    /* format chunk identifier */
    writeString(view, 12, 'fmt ');
    /* format chunk length */
    view.setUint32(16, 16, true);
    /* sample format (raw) */
    view.setUint16(20, 1, true);
    /* channel count */
    view.setUint16(22, numOfChan, true);
    /* sample rate */
    view.setUint32(24, sampleRate, true);
    /* byte rate (sample rate * block align) */
    view.setUint32(28, sampleRate * numOfChan * 2, true);
    /* block align (channel count * bytes per sample) */
    view.setUint16(32, numOfChan * 2, true);
    /* bits per sample */
    view.setUint16(34, 16, true);
    /* data chunk identifier */
    writeString(view, 36, 'data');
    /* data chunk length */
    view.setUint32(40, buffer.length * 2, true);

    // 写入 PCM 数据
    let offset = 44;
    for (let i = 0; i < buffer.length; i++, offset += 2) {
        const s = Math.max(-1, Math.min(1, buffer[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }

    return view;
}

function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
}

// // 播放所有录音
// document.getElementById('playRecordingsButton').onclick = () => {
//     const audioElements = recordingsBox.getElementsByTagName('audio');
//     playAudioSequence(Array.from(audioElements));
// };
//
// // 播放所有后端回复音频
// document.getElementById('playBackendRecordingsButton').onclick = () => {
//     playAudioSequence(backendAudioElements);
// };

// 播放音频序列的函数
function playAudioSequence(audioElements) {
    if (audioElements.length === 0) return;
    let index = 0;

    function playNext() {
        if (index < audioElements.length) {
            const audio = audioElements[index];
            audio.play();
            audio.onended = () => {
                index++;
                playNext();
            };
        }
    }

    playNext();
}

// 播放后端音频队列的函数，避免重复播放，并处理播放错误
function playBackendAudioQueue() {
    if (isPlayingBackendAudio || backendAudioQueue.length === 0) return;
    isPlayingBackendAudio = true;

    function playNext() {
        if (backendAudioQueue.length > 0) {
            const audio = backendAudioQueue.shift();

            // 获取音频源的 URL 和类型
            const src = audio.src;
            const type = audio.type || getAudioTypeFromSrc(src);

            // 定义错误处理函数
            const handleError = () => {
                const error = audio.error;
                console.error('音频播放失败:', {
                    src: src,
                    type: type,
                    errorCode: error ? error.code : '未知错误',
                    errorMessage: getErrorMessage(error)
                });

                // 检查浏览器支持的音频格式
                const supportedFormats = getSupportedAudioFormats();
                console.log('浏览器支持的音频格式:', supportedFormats);

                // 移除事件监听器，防止内存泄漏
                audio.removeEventListener('error', handleError);
                // 继续播放下一个音频
                playNext();
            };

            // 添加错误事件监听器
            audio.addEventListener('error', handleError);

            // 尝试播放音频，并处理可能的 Promise 拒绝
            const playPromise = audio.play();
            if (playPromise !== undefined) {
                playPromise
                    .then(() => {
                        // 播放成功，设置结束事件以播放下一个音频
                        audio.onended = () => {
                            // 移除错误事件监听器
                            audio.removeEventListener('error', handleError);
                            playNext();
                        };
                    })
                    .catch((error) => {
                        // 播放失败，记录错误信息
                        console.error('播放音频时发生错误:', {
                            src: src,
                            type: type,
                            error: error
                        });
                        // 移除错误事件监听器
                        audio.removeEventListener('error', handleError);
                        // 继续播放下一个音频
                        playNext();
                    });
            }
        } else {
            isPlayingBackendAudio = false;
        }
    }

    playNext();
}

// 辅助函数：从 URL 获取音频类型
function getAudioTypeFromSrc(src) {
    const extension = src.split('.').pop().toLowerCase();
    switch (extension) {
        case 'mp3':
            return 'audio/mpeg';
        case 'wav':
            return 'audio/wav';
        case 'ogg':
            return 'audio/ogg';
        case 'aac':
            return 'audio/aac';
        default:
            return 'unknown';
    }
}

// 辅助函数：获取浏览器支持的音频格式
function getSupportedAudioFormats() {
    const audio = document.createElement('audio');
    return {
        mp3: audio.canPlayType('audio/mpeg') ? 'Yes' : 'No',
        wav: audio.canPlayType('audio/wav') ? 'Yes' : 'No',
        ogg: audio.canPlayType('audio/ogg') ? 'Yes' : 'No',
        aac: audio.canPlayType('audio/aac') ? 'Yes' : 'No',
        flac: audio.canPlayType('audio/flac') ? 'Yes' : 'No'
    };
}

// 辅助函数：根据错误代码返回错误信息
function getErrorMessage(error) {
    if (!error) return '未知错误';
    switch (error.code) {
        case error.MEDIA_ERR_ABORTED:
            return '用户中止了音频播放。';
        case error.MEDIA_ERR_NETWORK:
            return '网络错误导致音频下载失败。';
        case error.MEDIA_ERR_DECODE:
            return '音频解码失败或音频文件损坏。';
        case error.MEDIA_ERR_SRC_NOT_SUPPORTED:
            return '音频格式不受支持。';
        default:
            return '未知错误。';
    }
}
