
const base_uri = "ws://localhost:42069/stream";
const request_uri = "http://localhost:42069/api/request_run";

const basic_config = {
    grid_width: 32,
    grid_height: 32,
    food: 50,
    snake_count: 1,
    map: "items"
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
        this.frames = [];
        this.last_frame = null;
    }

    /**
     *
     * @param {Uint8ClampedArray} base_map shape: (width * height * 4)
     */
    set_base_map(base_map) {
        console.log(base_map);
        this.last_frame = base_map.slice();
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
        this.frames = [];
        this.last_frame = null;
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
        const frame = new Uint8ClampedArray(this.last_frame);
        for (const pixel_data of pixel_changes_data) {
            const coord = pixel_data[0];
            const color = pixel_data[1];
            const index = (coord[0] + (coord[1] * this.total_width)) * 4;
            console.log(coord, color, index);
            for (let i = 0; i < 4; i++) {
                frame[index + i] = color[i];
            }
            frame[index + 3] = 255;
        }
        this.frames.push(frame);
        this.last_frame = frame.slice();
    }

}


class CanvasHandler {
    constructor() {
        this.canvas = document.getElementById('gameCanvas');
        this.context = this.canvas.getContext('2d');
        this.canvas.width = 800;
        this.canvas.height = 800;
        this.frame_handler = new FrameHandler();
        this.stream_handler = new StreamHandler();
        this.stream_handler.on_init_data = this.init.bind(this);
        this.stream_handler.set_msg_handler(this.frame_handler.add_frame.bind(this.frame_handler));
        this.frame_index = 0;
        this.frame_interval = 1 / 20; // 20 fps
        this.interval_id = null;
    }

    fillColor(color_rgb) {
        this.context.fillStyle = color_rgb;
        this.context.fillRect(0, 0, this.canvas.width, this.canvas.height);
    }

    init(init_data){
        console.log(init_data);
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

    show_frame(frame) {
        const img = new ImageData(frame, this.frame_handler.total_width);
        this.context.putImageData(img, 0, 0);
    }

    run() {
        this.interval_id = setInterval(() => {
            if (this.frame_index < this.frame_handler.frames.length) {
                this.show_frame(this.frame_handler.frames[this.frame_index]);
            }
            this.frame_index++;
        }, 100);
    }

    stop() {
        clearInterval(this.interval_id);
    }

}

class StreamHandler {
    constructor() {
        this.msg_handler = null;
        this.data_mode = "pixel_data";
        this.data_on_demain = false;
        this.init_data = null;
        this.on_init_data = null; // callback
        this.got_init_data = false;
        this.ws = null;
    }

    reset() {
        this.got_init_data = false;
        this.init_data = null;
        if (this.ws) {
            this.ws.close();
        }
    }

    async request_run(config){
        return fetch(request_uri, {
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
        const url = new URL(base_uri + "/" + stream_id);
        url.searchParams.append("data_on_demand", this.data_on_demain);
        url.searchParams.append("data_mode", this.data_mode);
        this.ws = new WebSocket(url.toString());
        this.ws.onmessage = this.msg_reciever.bind(this);
    }

    msg_reciever(message) {
        if (!this.got_init_data) {
            this.got_init_data = true;
            const init_data = JSON.parse(message.data);
            this.on_init_data(init_data);
        }
        else {
            // console.log(message.data);
            blobToArrayBuffer(message.data).then(data => {
                const view = new DataView(data);
                const pixels = [];
                for (let i = 0; i < view.byteLength; i += 5) {
                    const coord = [view.getUint8(i), view.getUint8(i + 1)];
                    const color = [view.getUint8(i + 2), view.getUint8(i + 3), view.getUint8(i + 4)];
                    pixels.push([coord, color]);
                }
                this.msg_handler(pixels);
            });
        }
    }

    send(msg) {
        this.ws.send(msg);
    }

    set_msg_handler(handler) {
        this.msg_handler = handler;
    }
}

const canvas_handler = new CanvasHandler();
const stream_handler = canvas_handler.stream_handler;
stream_handler.request_run(basic_config).then(stream_id => {
    console.log(stream_id);
    stream_handler.join_stream(stream_id);
    canvas_handler.run();
});
