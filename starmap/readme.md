
const starmapData = {
  "width": 1000,
  "height": 1000,
  "padding": 50,
  "owners": [
    { "id": 1, "name": "Player 1", "race": "Lizards", "color": "#00FF00" },
    { "id": 2, "name": "Player 2", "race": "Robots", "color": "#FF0000" }
  ],
  "planets": [
    { "x": 100, "y": 200, "owner": 1 },
    { "x": 300, "y": 800, "owner": 2 },
    { "x": 900, "y": 100, "owner": 0 }
  ],
  "starbases": [
    { "x": 300, "y": 800, "owner": 2 }
  ]
};

// --- Canvas drawing logic ---
const canvas = document.getElementById('starmap');
const ctx = canvas.getContext('2d');
const scaleX = canvas.width / (starmapData.width + 2 * starmapData.padding);
const scaleY = canvas.height / (starmapData.height + 2 * starmapData.padding);

function transformX(x) {
  return (x + starmapData.padding) * scaleX;
}

function transformY(y) {
  return (starmapData.height - y + starmapData.padding) * scaleY;
}

function getColor(ownerId) {
  const owner = starmapData.owners.find(o => o.id === ownerId);
  return owner ? owner.color : "#888888";
}

function drawCircle(x, y, radius, color) {
  ctx.beginPath();
  ctx.arc(x, y, r

