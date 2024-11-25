
const domain = `localhost:42069`;


const basic_config = {
    grid_width: 64,
    grid_height: 64,
    food: 50,
    food_decay: 0,
    snake_count: 2,
    map: "sign",
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
        this.frame_interval = 1 / 30; // 20 fps
        this.interval_id = null;
    }

    fillColor(color_rgb) {
        this.context.fillStyle = color_rgb;
        this.context.fillRect(0, 0, this.canvas.width, this.canvas.height);
    }

    async reset_stream_handler(host_domain) {
        if (this.stream_handler) {
            this.stream_handler.reset();
        }
        this.stream_handler = new StreamHandler(host_domain);
        this.stream_handler.on_init_data = this.init.bind(this);
        this.stream_handler.set_msg_handler(this.frame_handler.add_frame.bind(this.frame_handler));
        await this.stream_handler.protobuf_initialized;
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
        const free_tile_color = init_data.colorMapping[1];
        const base_map_frame = new Uint8ClampedArray(frame_width * frame_height * 4);
        // Fill the base map with the free tile color
        for (let i = 0; i < base_map_frame.length; i += 4) {
            for (let j = 0; j < 3; j++) {
                base_map_frame[i + j] = Object.values(free_tile_color)[j];
            }
            base_map_frame[i + 3] = 255;
        }
        for(let y = 0; y < init_data.baseMap.length; y++){
            for(let x = 0; x < init_data.baseMap[y].length; x++){
                const pixel_color = [0, 0, 0, 255];
                const expanded_coord = [(x*2) + offset_x, (y*2) + offset_y];
                const coord = [x, y];
                const tile_value = init_data.baseMap[y][x];
                const color = init_data.colorMapping[tile_value];
                Object.values(color).forEach((c, i) => {
                    pixel_color[i] = c;
                });
                let pixel_index = (expanded_coord[1] * frame_width + expanded_coord[0]) * 4;
                // write the pixel color to the base map frame
                for (let i = 0; i < 4; i++) {
                    base_map_frame[pixel_index + i] = pixel_color[i];
                }
                for(let dir of directions){
                    let new_expanded_coord = [expanded_coord[0] + dir[0], expanded_coord[1] + dir[1]];
                    let new_coord = [coord[0] + dir[0], coord[1] + dir[1]];
                    if(new_coord[0] >= 0 && new_coord[0] < init_data.baseMap[y].length && new_coord[1] >= 0 && new_coord[1] < init_data.baseMap.length){
                        if(init_data.baseMap[new_coord[1]][new_coord[0]] === tile_value){
                            const color = init_data.colorMapping[tile_value];
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
        // base_map_frame.fill(255);
        this.frame_handler.set_base_map(base_map_frame);
        this.show_frame(base_map_frame);
    }

    show_frame(frame_img) {
        const img_data = new ImageData(frame_img, this.frame_handler.total_width);
        this.context.putImageData(img_data, 0, 0);
    }

    run() {
        console.log("Running");
        console.log(this.frame_handler.frame_images);
        console.log(this.frame_index);
        this.interval_id = setInterval(() => {
            if (this.frame_index < this.frame_handler.frame_images.length) {
                this.show_frame(this.frame_handler.frame_images[this.frame_index]);
                this.frame_index++;
            }
        }, this.frame_interval * 1000);
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
        this.on_pixel_data = null; // callback
        this.got_init_data = false;
        this.ws = null;
        this.host_domain = host_domain;
        this.step_data_pb = null;
        this.proto_root = null;
        this.protobuf_initialized = this.init_protobuf();
    }

    async init_protobuf(){
        try{
            return protobuf.load("/static/sim_msgs.proto", (err, root) => {
                if (err) {
                    throw err;
                }
                this.proto_root = root;
            });
        }
        catch{
            console.log("Error loading protobuf");
        }
    }

    reset() {
        this.got_init_data = false;
        this.init_data = null;
        this.step_data_pb = null;
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
        this._process_msg(message.data);
    }

    _process_msg(data) {
        const MSG_TYPE = this.proto_root.lookupEnum("snakesim.MessageType");
        const msg_wrapper = this.proto_root.lookupType("snakesim.MsgWrapper");
        const message = msg_wrapper.decode(new Uint8Array(data));
        if (message.type == MSG_TYPE.values.PIXEL_CHANGES){
            let pixel_changes_type = this.proto_root.lookupType("snakesim.PixelChanges");
            let pixel_changes_proto = pixel_changes_type.decode(message.payload);
            let pixel_changes = pixel_changes_type.toObject(pixel_changes_proto, {
                defaults: true,
            });

            const pixel_changes_data = [];
            pixel_changes.pixels.forEach(pxl_data => {
                pixel_changes_data.push([
                    [
                        pxl_data.coord.x,
                        pxl_data.coord.y
                    ],
                    [
                        pxl_data.color.r,
                        pxl_data.color.g,
                        pxl_data.color.b
                    ]]);
            });
            this.msg_handler(pixel_changes_data);
        }
        else if (message.type == MSG_TYPE.values.RUN_META_DATA){
            let run_meta_data_type = this.proto_root.lookupType("snakesim.RunMetaData");
            let run_meta_data_proto = run_meta_data_type.decode(message.payload);
            let run_meta_data = run_meta_data_type.toObject(run_meta_data_proto, {
                defaults: true,
            });
            run_meta_data.baseMap = unflattenArray(run_meta_data.baseMap, run_meta_data.width);
            this.on_init_data(run_meta_data);
        }
        else{
            console.log("Unknown message type");

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
    await canvas_handler.reset_stream_handler(domain);
    canvas_handler.stream_handler.join_stream(stream_id);
    canvas_handler.run();
}


function unflattenArray(arr, width) {
    if (width <= 0) throw new Error("Width must be greater than 0");
    const height = Math.ceil(arr.length / width);
    const result = new Array(height);

    for (let i = 0; i < height; i++) {
        result[i] = arr.slice(i * width, (i + 1) * width);
    }

    return result;
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
