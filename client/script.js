
const domain = `localhost:42069`;

const basic_config = {
    grid_width: 64,
    grid_height: 64,
    food: 50,
    snake_count: 1,
    map: "sign"
};

function blobToArrayBuffer(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsArrayBuffer(blob);
    });
}

class FrameHandler {
    constructor() {
        this.width = null;
        this.height = null;
        this.content_offset_x = null;
        this.content_offset_y = null;
        this.pad_x = null;
        this.pad_y = null;
        this.total_width = null;
        this.total_height = null;
        this.frame_images = [];
        this.last_frame_data = null;
    }

    /**
     *
     * @param {Uint8ClampedArray} base_map shape: (width * height * 4)
     */
    set_base_map(base_map) {
        console.log(base_map);
        this.last_frame_data = base_map.slice();
    }

    init(width, height, content_offset_x, content_offset_y, pad_x, pad_y) {
        this.width = width;
        this.height = height;
        this.content_offset_x = content_offset_x;
        this.content_offset_y = content_offset_y;
        this.pad_x = pad_x;
        this.pad_y = pad_y;
        this.total_width = this.width + this.pad_x + this.content_offset_x;
        this.total_height = this.height + this.pad_y + this.content_offset_y;
    }

    clear() {
        this.frame_images = [];
        this.last_frame_data = null;
        this.width = null;
        this.height = null;
        this.content_offset_x = null;
        this.content_offset_y = null;
        this.pad_x = null;
        this.pad_y = null;
        this.total_width = null;
        this.total_height = null;
    }

    add_frame(pixel_changes_data) {
        const frame = new Uint8ClampedArray(this.last_frame_data);
        for (const pixel_data of pixel_changes_data) {
            const coord = pixel_data[0];
            const color = pixel_data[1];
            const index = (coord[0] + (coord[1] * this.total_width)) * 4;
            for (let i = 0; i < 4; i++) {
                frame[index + i] = color[i];
            }
            frame[index + 3] = 255;
        }
        this.frame_images.push(frame);
        this.last_frame_data = frame.slice();
    }

}


class CanvasHandler {
    constructor() {
        this.canvas = document.getElementById('gameCanvas');
        this.context = this.canvas.getContext('2d');
        this.canvas.width = 800;
        this.canvas.height = 800;
        this.frame_handler = new FrameHandler();
        this.stream_handler = null;
        this.reset_stream_handler(domain); // creates a new stream handler
        this.frame_index = 0;
        this.frame_interval = 1 / 20; // 20 fps
        this.interval_id = null;
    }

    fillColor(color_rgb) {
        this.context.fillStyle = color_rgb;
        this.context.fillRect(0, 0, this.canvas.width, this.canvas.height);
    }

    reset_stream_handler(host_domain) {
        if (this.stream_handler) {
            this.stream_handler.reset();
        }
        this.stream_handler = new StreamHandler(host_domain);
        this.stream_handler.on_init_data = this.init.bind(this);
        this.stream_handler.set_msg_handler(this.frame_handler.add_frame.bind(this.frame_handler));
    }

    start_stream(stream_id) {
        this.reset_stream_handler(domain);
        this.stream_handler.join_stream(stream_id);
        this.run();
    }

    init(init_data){
        this.frame_handler.init(init_data.width * 2, init_data.height * 2, 1, 1, 0, 0);
        this.canvas.width = this.frame_handler.total_width;
        this.canvas.height = this.frame_handler.total_height;
        const frame_width = this.canvas.width;
        const frame_height = this.canvas.height;
        let directions = [[1,0], [0,1], [-1,0], [0,-1]];
        const offset_x = this.frame_handler.content_offset_x;
        const offset_y = this.frame_handler.content_offset_y;
        const free_tile_color = init_data.color_mapping[1];
        const base_map_frame = new Uint8ClampedArray(frame_width * frame_height * 4);
        // Fill the base map with the free tile color
        for (let i = 0; i < base_map_frame.length; i += 4) {
            for (let j = 0; j < 3; j++) {
                base_map_frame[i + j] = free_tile_color[j];
            }
            base_map_frame[i + 3] = 255;
        }
        for(let y = 0; y < init_data.base_map.length; y++){
            for(let x = 0; x < init_data.base_map[y].length; x++){
                const pixel_color = [0, 0, 0, 255];
                const expanded_coord = [(x*2) + offset_x, (y*2) + offset_y];
                const coord = [x, y];
                const tile_value = init_data.base_map[y][x];
                const color = init_data.color_mapping[tile_value];
                for (const i in color) {
                    pixel_color[i] = color[i];
                }
                let pixel_index = (expanded_coord[1] * frame_width + expanded_coord[0]) * 4;
                // write the pixel color to the base map frame
                for (let i = 0; i < 4; i++) {
                    base_map_frame[pixel_index + i] = pixel_color[i];
                }
                for(let dir of directions){
                    let new_expanded_coord = [expanded_coord[0] + dir[0], expanded_coord[1] + dir[1]];
                    let new_coord = [coord[0] + dir[0], coord[1] + dir[1]];
                    if(new_coord[0] >= 0 && new_coord[0] < init_data.base_map[y].length && new_coord[1] >= 0 && new_coord[1] < init_data.base_map.length){
                        if(init_data.base_map[new_coord[1]][new_coord[0]] === tile_value){
                            const color = init_data.color_mapping[tile_value];
                            for (const i in color) {
                                pixel_color[i] = color[i];
                            }
                            pixel_index = (new_expanded_coord[1] * frame_width + new_expanded_coord[0]) * 4;
                            for (let i = 0; i < 4; i++) {
                                base_map_frame[pixel_index + i] = pixel_color[i];
                            }
                        }
                    }
                }
            }
        }
        this.frame_handler.set_base_map(base_map_frame);
    }

    show_frame(frame_img) {
        const img_data = new ImageData(frame_img, this.frame_handler.total_width);
        this.context.putImageData(img_data, 0, 0);
    }

    run() {
        this.interval_id = setInterval(() => {
            if (this.frame_index < this.frame_handler.frame_images.length) {
                this.show_frame(this.frame_handler.frame_images[this.frame_index]);
                this.frame_index++;
            }
        }, 100);
    }

    stop() {
        this.frame_index = 0;
        clearInterval(this.interval_id);
    }

}

class StreamHandler {
    constructor(host_domain) {
        this.msg_handler = null;
        this.data_mode = "pixel_data";
        this.data_on_demain = false;
        this.init_data = null;
        this.on_init_data = null; // callback
        this.got_init_data = false;
        this.ws = null;
        this.host_domain = host_domain;
    }

    reset() {
        this.got_init_data = false;
        this.init_data = null;
        if (this.ws) {
            this.ws.close();
        }
    }

    async request_run(config){
        const request_url = `http://${this.host_domain}/api/request_run`

        return fetch(request_url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(config)
        }).then(response => {
            return response.json();
        }).then(data => {
            return data.stream_id;
        }).catch(error => {
            console.error('Error:', error);
        });
    }

    join_stream(stream_id){
        const stream_url = `http://${this.host_domain}/stream/${stream_id}`; 
        const url = new URL(stream_url);
        url.searchParams.append("data_on_demand", this.data_on_demain);
        url.searchParams.append("data_mode", this.data_mode);
        this.ws = new WebSocket(url.toString());
        this.ws.onmessage = this.msg_reciever.bind(this);
        this.ws.binaryType = "arraybuffer";
    }

    msg_reciever(message) {
        if (!this.got_init_data) {
            this.got_init_data = true;
            const init_data = JSON.parse(message.data);
            this.on_init_data(init_data);
        }
        else {
            // console.log(message.data);
            const data = message.data;
            const view = new DataView(data);
            const pixels = [];
            for (let i = 0; i < view.byteLength; i += 5) {
                const coord = [view.getUint8(i), view.getUint8(i + 1)];
                const color = [view.getUint8(i + 2), view.getUint8(i + 3), view.getUint8(i + 4)];
                pixels.push([coord, color]);
            }
            this.msg_handler(pixels);
        }
    }

    send(msg) {
        this.ws.send(msg);
    }

    set_msg_handler(handler) {
        this.msg_handler = handler;
    }
}


function populate_stream_list(streams) {
    const stream_list = document.getElementById('activeStreamsList');
    stream_list.innerHTML = '';
    for (const stream of streams) {
        const stream_item = document.createElement('li');
        stream_item.appendChild(document.createTextNode(stream));
        stream_item.onclick = start_stream_event;
        stream_list.appendChild(stream_item);
    }
}

async function get_active_streams() {
    const url = `http://${domain}/api/run_info`;
    return await fetch(url).then(response => {
        return response.json();
    }).then(data => {
        const stream_ids = Object.keys(data);
        populate_stream_list(stream_ids);
        return data;
    }).catch(error => {
        console.error('Error:', error);
    });

}

async function start_stream_event(event) {
    canvas_handler.stop();
    stream_id = event.target.innerText;
    console.log(stream_id);
    const run_info = await get_active_streams();
    console.log(run_info);
    const current_step = run_info[stream_id].steps;
    canvas_handler.frame_index = current_step * 2;
    canvas_handler.frame_handler.clear();
    canvas_handler.reset_stream_handler(domain);
    canvas_handler.stream_handler.join_stream(stream_id);
    canvas_handler.run();
}


const canvas_handler = new CanvasHandler();
document.addEventListener('DOMContentLoaded', () =>{
    get_active_streams();
});
document.getElementById('requestButton').onclick = () => {
    const stream_handler = canvas_handler.stream_handler;
    stream_handler.request_run(basic_config).then(stream_id => {
        get_active_streams();
    });
};
