

    const NATIVES = {
      '0': '',
      '1': 'Hum',
      '2': 'Bov',
      '3': 'Rep',
      '4': 'Av',
      '5': 'Amorph',
      '6': 'Ins',
      '7': 'Amph',
      '8': 'Ghip',
      '9': 'Sil'
    };

    const NATIVE_COLORS = {
      '0': '#888',
      '1': "#0088ff",
      '2': "yellow",
      '3': "#44ff44",
      '4': "white",
      '5': "#ff4444",
      '6': "white",
      '7': "cyan",
      '8': "#0088ff",
      '9': "cyan",
    };

    const GOVT = {
      '0': '',
      '1': '1-Anarc',
      '2': '2-PreT',
      '3': '3-ErlT',
      '4': '4-Trib',
      '5': '5-Feud',
      '6': '6-Mon',
      '7': '7-Repr',
      '8': '8-Par',
      '9': '9-Unity'
    };

    const TEMP_COLOURS = [
      "#4961d2", // 0
      "#5875e1", // 1
      "#6788ee", // 5
      "#779af7", // 10
      "#88abfd", // 15
      "#9abbff", // 20
      "#aac7fd", // 25
      "#bad0f8", // 30
      "#c9d7f0", // 35
      "#d6dce4", // 40
      "#e9f7df", // 50
      "#faf3d4", // 60
      "#f7d0bc", // 70
      "#f7b89c", // 75
      "#f7a889", // 80
      "#f39475", // 85
      "#ec7f63", // 90
      "#e26952", // 95
      "#d55042", // 99
      "#c53334", // 100
    ]

    const RESOURCE_COLOURS = {
      'neutronium': "#FFE1D5",
      'duranium': "#DAD8CE",
      'tritanium': "#92BFDB",
      'molybdenum': "#E47DA8",
      'megacredits': "#ECCB60",
    }

    const CLAN_THRESHOLDS = [0, 1, 2, 5, 
                       10, 20, 50, 60, 70, 80, 90,
                       100, 200, 500, 600, 700, 800, 900,
                       1_000, 2_000, 5_000, 6_000, 7_000, 8_000, 9_000,
                       10_000, 20_000, 30_000, 40_000, 50_000,
                       60_000, 70_000, 80_000, 90_000, 100_000,
                       200_000]

    const THRESHOLDS = [0, 1, 2, 5,
                  10, 20, 30, 40, 50, 60, 70, 80, 90,
                  100, 200, 300, 400, 500, 600, 700, 800, 900,
                  1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000,
                  10_000, 20_000, 30_000, 40_000, 50_000]

    const TEMP_THRESHOLDS = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 75, 80, 85, 90, 95, 99, 100]

    function tval(val, thresholds) {
      return thresholds[parseInt(val, 36)];
    }

    function nval(val, names) {
      return names[val];
    }

    function buildEcon(econrec) {
      const [temp, nativetype, nativegovernment, nativeclans, clans, megacredits, neutronium, molybdenum, duranium, tritanium, groundneutronium, groundmolybdenum, groundduranium, groundtritanium] = econrec;
      return {
        temp:             tval(temp, TEMP_THRESHOLDS),
        tempColor:        tval(temp, TEMP_COLOURS),
        nativeRace:       nval(nativetype, NATIVES),
        nativeColor:      nval(nativetype, NATIVE_COLORS),
        government:       nval(nativegovernment, GOVT),
        nativeClans:      tval(nativeclans, CLAN_THRESHOLDS),
        clans:            tval(clans, CLAN_THRESHOLDS),
        megacredits:      tval(megacredits, THRESHOLDS),
        neutronium:       tval(neutronium, THRESHOLDS),
        molybdenum:       tval(molybdenum, THRESHOLDS),
        duranium:         tval(duranium, THRESHOLDS),
        tritanium:        tval(tritanium, THRESHOLDS),
        groundneutronium: tval(groundneutronium, THRESHOLDS),
        groundmolybdenum: tval(groundmolybdenum, THRESHOLDS),
        groundduranium:   tval(groundduranium, THRESHOLDS),
        groundtritanium:  tval(groundtritanium, THRESHOLDS)
      };
    }

    /**
     * Map “val” onto a [0..3] width and a [0..10] height.
     * For any v < 11, returns {0,0}.
     */
    function getWedgeWidthAndHeight(val) {
      if (val < 11) {
        return {width: 0, height: 0};
      }
      const n = val - 1;
      const width = Math.min(3, Math.trunc(Math.log10(n)));
      const divisor = 10 ** width;
      const height = Math.min(Math.round(n / divisor), 10);
      return {width, height};
    }

    function drawResources(ctx, x, y, econ) {
      const wedge   = 2 * Math.PI / 24;    // one “unit” of arc
      const baseH   = 20;                  // minimum radius
      const deltaH  = 5;                   // extra radius per height unit
      
      const rsrcs = [
        "neutronium",
        "duranium",
        "tritanium",
        "molybdenum",
        "megacredits"
      ];
      
      // 1) collect width/height units for each resource
      const vals = {};
      rsrcs.forEach(rsrc => {
        vals[rsrc] = getWedgeWidthAndHeight(econ[rsrc]);
      });
      
      // 2) total up all the “width” units, then convert to arc
      const totalUnits = rsrcs.reduce((sum, rsrc) => sum + vals[rsrc].width, 0);
      const totalArc   = totalUnits * wedge;
      
      // 3) start six wedges counter-clockwise, then shift back by half of totalArc
      let angle = -6 * wedge - (totalArc / 2);
      
      // 4) draw each slice in turn
      rsrcs.forEach(rsrc => {
        const { width, height: hUnits } = vals[rsrc];
        const arc      = width * wedge;
        const radius   = baseH + hUnits * deltaH;
        const nextAngle = angle + arc;
        
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.arc(x, y, radius, angle, nextAngle);
        ctx.fillStyle = RESOURCE_COLOURS[rsrc];
        ctx.fill();
        
        angle = nextAngle;
      });
    }

    function drawGroundResources(ctx, x, y, econ) {
      const wedge   = 2 * Math.PI / 24;    // one “unit” of arc
      const baseH   = 20;                  // minimum radius
      const deltaH  = 5;                   // extra radius per height unit
      
      const rsrcs = [
        "groundneutronium",
        "groundduranium",
        "groundtritanium",
        "groundmolybdenum",
        // "megacredits" TODO income potential
      ];
      
      // 1) collect width/height units for each resource
      const vals = {};
      rsrcs.forEach(rsrc => {
        vals[rsrc] = getWedgeWidthAndHeight(econ[rsrc]);
      });
      
      // 2) total up all the “width” units, then convert to arc
      const totalUnits = rsrcs.reduce((sum, rsrc) => sum + vals[rsrc].width, 0);
      const totalArc   = totalUnits * wedge;
      
      // 3) start six wedges clockwise, then shift back by half of totalArc
      let angle = 6 * wedge + (totalArc / 2);
      
      // 4) draw each slice in turn
      rsrcs.forEach(rsrc => {
        const { width, height: hUnits } = vals[rsrc];
        const arc      = width * wedge;
        const radius   = baseH + hUnits * deltaH;
        const nextAngle = angle - arc;
        
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.arc(x, y, radius, angle, nextAngle, true);
        ctx.fillStyle = RESOURCE_COLOURS[rsrc.substring(6)];
        ctx.fill();
        
        angle = nextAngle;
      });
    }

    /**
     * Returns the last updated econ value for a given planet and turn
     */
    function getPlanetStats(planetId, turnId) {
      if (turnId < 1) {
        return "unknown";
      }
      const turnData = econreportData[turnId - 1] || {};
      return turnData.hasOwnProperty(planetId) ? turnData[planetId] : getPlanetStats(planetId, turnId - 1);
    }

    function drawCircle(ctx, x, y, radius, color) {
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();
    }

    function drawRect(ctx, x, y, width, height, color) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.strokeRect(x, y, width, height);
    }

    function drawPopn(ctx, x, y, clans, color) {
      if (clans == 1) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + 8, y);
        ctx.stroke();
        return;
      }
      if (clans < 10) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + 8, y);
        ctx.moveTo(x, y - 4);
        ctx.lineTo(x + 8, y - 4);
        ctx.stroke();
        return;
      }

      let log10 = Math.min(Math.trunc(Math.log10(clans)), 5);
      let div = Math.pow(10, log10);
      let boxes = Math.min(Math.round(clans / div), 12);
      let bars = log10;
      let height = log10 * 2 + 2;
      let width = log10 * 4 + 4;

      let y1 = y - height;
      for (let i = 0; i < boxes; i++) {
        let y2 = y1 - ((height + 2) * i);
        drawRect(ctx, x, y2, width, height, color);
        if (i % 3 == 2) {
          ctx.beginPath();
          ctx.moveTo(x, y2 + 1);
          ctx.lineTo(x + width, y2 + 1);
          ctx.stroke();
        }
        for (let j = 1; j < bars; j++) {
          ctx.beginPath();
          ctx.moveTo(x + width - j, y2);
          ctx.lineTo(x + width - j, y2 + height);
          ctx.stroke();
        }
      }
    }

    function drawNativePopn(ctx, x, y, clans, color) {
      if (clans == 1) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x - 8, y);
        ctx.stroke();
        return;
      }
      if (clans < 10) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x - 8, y);
        ctx.moveTo(x, y - 4);
        ctx.lineTo(x - 8, y - 4);
        ctx.stroke();
        return;
      }

      let log10 = Math.min(Math.trunc(Math.log10(clans)), 5);
      let div = Math.pow(10, log10);
      let boxes = Math.min(Math.round(clans / div), 12);
      let bars = log10;
      let height = log10 * 2 + 2;
      let width = log10 * 4 + 4;
      let y1 = y - height;
      for (let i = 0; i < boxes; i++) {
        let y2 = y1 - ((height + 2) * i);
        drawRect(ctx, x - width, y2, width, height, color);
        if (i % 3 == 2) {
          ctx.beginPath();
          ctx.moveTo(x, y2 + 1);
          ctx.lineTo(x - width, y2 + 1);
          ctx.stroke();
        }
        for (let j = 1; j < bars; j++) {
          ctx.beginPath();
          ctx.moveTo(x - width + j, y2);
          ctx.lineTo(x - width + j, y2 + height);
          ctx.stroke();
        }
      }
    }

    function updateInfo() {
      const header = document.querySelector('#infoBox .header');
      const footer = document.querySelector('#infoBox .footer');
      const planet = starmapData.planets.find(p => p.id === targetPlanetId);
      const starbaseSet = new Set(starmapData.starbases[currentTurnId - 1] || []);
      let starbase = starbaseSet.has(targetPlanetId)
      if (!planet) {
        return;
      }
      const ownerid = getPlanetOwners(currentTurnId)[targetPlanetId];
      let ownerLabel = "Unowned";
      if (ownerid) {
        const player = starmapData.players.find(p => p.id === ownerid);
        ownerLabel = `[${ownerid}] ${player.race}`;
      }
      const econrec = getPlanetStats(targetPlanetId, currentTurnId);
      const econ = buildEcon(econrec);
      const color = getColor(ownerid);

      const ctx = infoBoxCtx;
      const size = infoBoxCanvas.width;
      ctx.clearRect(0, 0, size, size);
      drawRect(ctx, 0, 0, size, size, color);

      // owner
      ctx.font          = `12px sans-serif`;

      ctx.textAlign     = 'left';
      ctx.textBaseline  = 'middle';
      ctx.fillStyle     = color;
      ctx.fillText(ownerLabel, 8, size - 10);

      // temp
      ctx.textAlign     = 'right';
      ctx.fillStyle     = econ.tempColor;
      ctx.fillText(`${econ.temp}°`, size - 6, 12);

      drawResources(ctx, size/2, size/2, econ);
      drawGroundResources(ctx, size/2, size/2, econ);

      // draw the planet
      drawCircle(ctx, size/2, size/2, 20, econ.tempColor);

      if (starbase) {
        ctx.font          = `12px sans-serif`;
        ctx.textAlign     = 'right';
        ctx.textBaseline  = 'middle';
        ctx.fillStyle     = color;
        ctx.fillText('⨁', size/2 + 23, size/2 - 12);
      }

      if (econ.nativeRace) {
        ctx.textAlign     = 'rights';
        ctx.textBaseline  = 'middle';
        ctx.fillStyle     = econ.nativeColor;
        ctx.fillText(`${econ.government} ${econ.nativeRace}`, size - 6, size - 10);
        drawNativePopn(ctx, size - 6, size - 20, econ.nativeClans, "#fff");
      }

      if (ownerid) {
        drawPopn(ctx, 6, size - 20, econ.clans, color);
      }

      header.innerHTML = `<strong>P${planet.id}-${planet.name}</strong><br>`
      footer.innerHTML = `x: ${planet.x}, y: ${planet.y}`;
    }