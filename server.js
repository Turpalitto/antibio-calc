const http = require('http');
const fs = require('fs');
const path = require('path');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon'
};

const server = http.createServer((req, res) => {
  let file = req.url === '/' ? '/antibiotic_calc.html' : req.url.split('?')[0];
  file = path.join(__dirname, file);

  const ext = path.extname(file).toLowerCase();
  const mime = MIME[ext] || 'application/octet-stream';

  try {
    const data = fs.readFileSync(file);
    res.writeHead(200, { 'Content-Type': mime });
    res.end(data);
    console.log(`200 ${req.url} (${data.length}b)`);
  } catch (e) {
    res.writeHead(404);
    res.end('404 Not Found');
    console.log(`404 ${req.url}`);
  }
});

const PORT = process.env.PORT || 8080;
server.listen(PORT, '0.0.0.0', () => {
  console.log('Server: http://0.0.0.0:' + PORT);
});
