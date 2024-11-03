console.log('script.js');

const WS_URL = 'ws://homeserver:42069/ws';

const basic_config = {
    grid_width: 32,
    grid_height: 32,
    food_count: 15,
    nr_of_snakes: 1,
    data_mode: "pixel_data",
    data_on_demain: false,
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

class CanvasHandler {
  constructor() {
    this.canvas = document.getElementById('gameCanvas');
    this.context = this.canvas.getContext('2d');
    this.canvas.width = 800;
    this.canvas.height = 800;
  }

  fillColor(color_rgb) {
    this.context.fillStyle = color_rgb;
    this.context.fillRect(0, 0, this.canvas.width, this.canvas.height);
  }

  init_map(meta_data){
    this.canvas.height = (meta_data.height * 2) + 1;
    this.canvas.width = (meta_data.width * 2) + 1;
    let directions = [[1,0], [0,1], [-1,0], [0,-1]];
    for(let y = 0; y < meta_data.base_map.length; y++){
        for(let x = 0; x < meta_data.base_map[y].length; x++){
            let pixel = this.context.createImageData(1, 1);
            const expanded_coord = [x*2, y*2];
            const coord = [x, y];
            const tile_value = meta_data.base_map[y][x];
            const color = meta_data.color_mapping[tile_value];
            for (const i in color) {
                pixel.data[i] = color[i];
            }
            pixel.data[3] = 255;
            this.context.putImageData(pixel, expanded_coord[0], expanded_coord[1]);
            for(let dir of directions){
                let new_expanded_coord = [expanded_coord[0] + dir[0], expanded_coord[1] + dir[1]];
                let new_coord = [coord[0] + dir[0], coord[1] + dir[1]];
                if(new_coord[0] >= 0 && new_coord[0] < meta_data.base_map[y].length && new_coord[1] >= 0 && new_coord[1] < meta_data.base_map.length){
                    if(meta_data.base_map[new_coord[1]][new_coord[0]] === tile_value){
                        let pixel = this.context.createImageData(1, 1);
                        const color = meta_data.color_mapping[tile_value];
                        for (const i in color) {
                            pixel.data[i] = color[i];
                        }
                        pixel.data[3] = 255;
                        this.context.putImageData(pixel, new_expanded_coord[0], new_expanded_coord[1]);
                    }
                }
            }
        }
    }

  }

  draw_pixels(pixels) {
    for (const pixel_data of pixels) {
      let pixel = this.context.createImageData(1, 1);
      const coord = pixel_data[0];
      const color = pixel_data[1];
      for (const i in color) {
        pixel.data[i] = color[i];
      }
      pixel.data[3] = 255;
      this.context.putImageData(pixel, coord[0], coord[1]);
    }
  }
}

class WebSocketHandler {
    constructor() {
        this.ws = new WebSocket(WS_URL);
        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.send(JSON.stringify(basic_config));
        };
        this.msg_nr = 0;
        this.ws.onmessage = this.msg_reciever.bind(this);
        this.msg_handler = null;
    }

    msg_reciever(message) {
        this.msg_nr++;
        if (this.msg_nr === 2) {
            let run_metadata = JSON.parse(message.data);
            canvas_handler.init_map(run_metadata);
        }
        else if (this.msg_nr > 2) {
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
            // this.msg_handler(data);
        }
    }

    send(msg) {
        this.ws.send(msg);
    }

    set_msg_handler(inst, handler) {
        this.msg_handler = handler.bind(inst);
    }
}

const canvas_handler = new CanvasHandler();
const ws_handler = new WebSocketHandler();
ws_handler.set_msg_handler(canvas_handler, canvas_handler.draw_pixels);
canvas_handler.fillColor('rgb(0, 0, 0)');