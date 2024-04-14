	class MapDimensions {
		referencesize = 50000;
		metersPerPixel = 100;
		pixelsPerTile = 256;
		factorx = 1;
		factory = 1;
		minzoom = 3;
		maxzoom = 8;
	}

	async function fantasyMap(mapLocation, mapDim, locationsList, useCustomMarkerIcon, customMarkers) { 
			
			L.Projection.hex = L.extend({}, L.Projection.LongLat, {
				project: function (latlng) {
					return L.point(latlng.lng / mapDim.pixelsPerTile, latlng.lat / mapDim.pixelsPerTile);
				},

				unproject: function (point) {
				
					return new L.latLng(point.y * mapDim.pixelsPerTile, point.x * mapDim.pixelsPerTile);
				},

				bounds: L.bounds([-180, -90], [180, 90])			
			});
		
			L.CRS.pr = L.extend({}, L.CRS.Simple, {
			  projection: L.Projection.hex,
			  transformation: new L.Transformation(mapDim.factorx, (mapDim.referencesize / mapDim.pixelsPerTile) / 2, -mapDim.factory, (mapDim.referencesize / mapDim.pixelsPerTile) / 2),

			  scale: function(zoom) {
				return Math.pow(2, zoom);
			  },

			  zoom: function(scale) {
				return Math.log(scale) / Math.LN2;
			  },

			  distance: function(latlng1, latlng2) {
				var dx = (latlng2.lng - latlng1.lng) * mapDim.metersPerPixel,
				  dy = (latlng2.lat - latlng1.lat) * mapDim.metersPerPixel;

				return Math.sqrt(dx * dx + dy * dy);
			  },
			  infinite: true
			});
	  
		//Creating the Map
		var map = L.map('map',
			{
				crs: L.CRS.pr,
				fullscreenControl: true,
			}
		);
		
		var layerDisplayGroups = {}
		
		var mapBounds = new L.LatLngBounds(
		map.unproject([0, mapDim.referencesize], 8),
		map.unproject([mapDim.referencesize, 0], 8));
		map.setMaxBounds(mapBounds);

		var mapCenter = map.unproject([mapDim.referencesize/2, mapDim.referencesize/2], 8);
		
		L.tileLayer.wms(mapLocation, {
		  continuousWorld: false,
		  bounds: mapBounds,
		  noWrap: true,  
		  minZoom: mapDim.minzoom,
		  maxZoom: mapDim.maxzoom,
		  format: 'image/png',
		  transparent: true,	  
		  crs: L.CRS.Simple
		}).addTo(map);	
		
		L.control.scale({metric: true, maxWidth: 130}).addTo(map);	
		initAjaxGeoJSON(layerDisplayGroups);
		
		for (var geoData in locationsList) {
			console.log("Loading: " + locationsList[geoData]);
			loadGeoJSON(locationsList[geoData], map);;
		}	
		
		console.log("Locations list read.");
		
		locationFinder(map);
		setInitialLocation(map);
		
		console.log("Done setting up the map!");		
		
		return map;
	}
	
	/* investigate the URL for specific location to view, and set the map to that */
	function setInitialLocation(map) {
		var passedLat = parseInt(getQueryStringValue("lat"), 0);
		var passedLng = parseInt(getQueryStringValue("lng"), 0);
		var passedZoom = parseInt(getQueryStringValue("zoom"), 0);
		
		if (passedLat != 0) {
			console.log("Requested location: " + passedLat + ", " + passedLng + ", Zoom: " + passedZoom);		
			map.setView([passedLat, passedLng], passedZoom);
		} else {
			console.log("No requested location.");
			map.setView([-38, 35], 6);
		}
	}
		
	function layerStyle (feature) {
		var default_style = {
			"color" : "#eaeaea",
			"weight" : ".3",
			"opacity" : "0.0",
			"fillColor" : "#eaeaea",
			"fillOpacity" : "0.0"
		};
		var rewrite_keys = {
			'stroke' : 'color',
			'stroke-width' : 'weight',
			'stroke-opacity' : 'opacity',
			'fill' : 'fillColor',
			'fill-opacity' : 'fillOpacity',
		};	
		var props = feature.properties || {};
		var style = {};
		function camelFun (_, first_letter) {
			return first_letter.toUpperCase();
		};
		for (var key in props) {
			if (key.match('-')) {
				var camelcase = key.replace(/-(\w)/, camelFun);
				style[ camelcase ] = props[ key ];
			}
			// rewrite style keys from geojson.io
			if (rewrite_keys[ key ]) {
				style[ rewrite_keys[ key ] ] = props[ key ];
			}
		}
		return L.Util.extend(style, default_style);
	}
	
	function onEachFeature (feature, layer) {
		var props = feature.properties || {};
		var text = props["popup-text"] || "";
		if (text) {
			layer.bindPopup( text );
		}
	}
	
	function pointToLayer (feature, latlng) {
		var markerOptions = {};			// See https://leafletjs.com/reference.html#marker for options
		var props = feature.properties || {};
		var markerKey = props["marker-group"] || "";		
		var customIconURL  = customMarkers["Default"];
		
		if (customMarkers.hasOwnProperty(markerKey)) {
			customIconURL = customMarkers[markerKey];
		}		
		
		var customIcon = L.icon({
			iconUrl: 		customIconURL,
			shadowUrl: 		'https://pathfinder-gm-tools.s3.amazonaws.com/map/MerisylMapLocationMarkerShadow.png',

			iconSize:     	[30, 42], 	// size of the icon
			shadowSize:   	[26, 38], 	// size of the shadow
			iconAnchor:   	[15, 42], 	// point of the icon which will correspond to marker's location
			shadowAnchor: 	[02, 38],  	// the same for the shadow
			popupAnchor:  	[00, -20] 	// point from which the popup should open relative to the iconAnchor
		});		

		if (useCustomMarkerIcon) {
			markerOptions["icon"] = customIcon;   
		}
		
		return L.marker(latlng, markerOptions);
	}	
		
		
	async function loadGeoJSON(targetfile, map) {
		return new Promise(resolve => {
			var layer = L.ajaxGeoJson(targetfile, {
				style : layerStyle,
				onEachFeature : onEachFeature,
				pointToLayer: pointToLayer
			});	
		
			console.log("Adding layer to map.");
			layer.addTo(map);
		});
	}
	
	function initAjaxGeoJSON(layerDisplayGroups) {
		L.AjaxGeoJSON = L.GeoJSON.extend({
		  options: {
			type: 'json', // 'json|kml|gpx'
		  },

		  initialize: function (url, options) {
			L.setOptions(this, options);
			this._url = url;
			this.layer = L.geoJson(null, this.options);
			this.layer.isGeo = true;
		  },

		  onAdd: function (map) {
			var _this = this;
			var type = this.options.type;
			var xhr;

			console.log("triggered onAdd");

			this.map = map;

			map.addLayer(this.layer);

			if (!this.request) {
			  this.request = xhr = new XMLHttpRequest();

			  xhr.onreadystatechange = function () {
				var data;
				if (xhr.readyState === xhr.DONE && xhr.status === 200) {
				  if (type === 'json') {
					data = JSON.parse(xhr.responseText);
				  } else if (['kml', 'gpx'].indexOf(type) !== -1) {
					data = window.toGeoJSON[type](xhr.responseXML);
				  }
				  _this.json = data;
				  _this.layer.addData(data);
				  
				  organizeClusters(map, layerDisplayGroups);
				  
				  _this.fire('ready');
				}
			  };

			  xhr.open('get', this._url, true);

			  xhr.send();
			}
			this.fire('add');
		  },

		  eachLayer: function (fnc) {
			this.layer.eachLayer(fnc);
		  },

		  setStyle: function (style) {
			this.layer.setStyle(style);
		  },

		  resetStyle: function (layer) {
			this.layer.resetStyle(layer);
		  },

		  onRemove: function (map) {
			this.map.removeLayer(this.layer);
		  },

		  getBounds: function () {
			return this.layer.getBounds();
		  },
		});

		L.ajaxGeoJson = function (url, options) {
		  return new L.AjaxGeoJSON(url, options);
		};
	}	

	function locationFinder(map) {
		//Coordinate Finder
		var marker = L.marker([0, 0], {
		  draggable: true,
		}).addTo(map);
		
		marker.bindPopup('Location Finder').openPopup();
		marker.on('dragend', function(e) {
		  marker.getPopup().setContent(JSON.stringify(marker.toGeoJSON())).openOn(map);
		});	
	}
	
	/* Given a marker-group key, return the corresponding layer group to display, or create it if not already present */
	function displayGroup(key, clusterGroup, layerDisplayGroups) {
		var ldg;
		
		if (layerDisplayGroups.hasOwnProperty(key)) {
			ldg = layerDisplayGroups[key];
		} else {
			ldg = L.featureGroup.subGroup(
				clusterGroup,
				null,
			);
			layerDisplayGroups[key] = ldg;
			clusterGroup.addLayer(ldg);
		}
		
		return ldg;
	}
	
	function organizeClusters(map, layerDisplayGroups) {
		console.log("Organizing clusters.");
		// L.DomUtil.TRANSITION = true;
		
		var clusterGroup = L.markerClusterGroup({
			iconCreateFunction: function(cluster) {
				var markers = cluster.getAllChildMarkers();
				var html = '<div class="cluster">' + markers.length + '</div>';
				return L.divIcon({ html: html, className: 'clusterIcon', iconSize: L.point(32, 32) });
			},
			spiderfyOnMaxZoom: false, 
			showCoverageOnHover: true, 
			zoomToBoundsOnClick: true,
			animate: false
		}); 
		
		map.eachLayer(function(layer){
			if (layer.isGeo) {
				console.log("Identified GEO layer");
				
				// map.removeLayer(layer);  TODO: Figure out why in refactored mode this line prevents successful loading of multiple layers.
				layer.eachLayer(function (sublayer) {
					var feature = sublayer.toGeoJSON();
					
					console.log(JSON.stringify(feature));
					
					var props = feature.properties || {};
					var layerKey = props["marker-group"] || "";
					if (layerKey) {
						var layergroup = displayGroup(layerKey, clusterGroup, layerDisplayGroups); 
						layergroup.addLayer(sublayer);
						layer.remove(sublayer);
						console.log("Added to layergroup: " + layerKey);
					} else {
						clusterGroup.addLayer(sublayer);
						layer.remove(sublayer);
					}
				});
				// clusterGroup.addLayer(layer);
			}
		});
		
		
		Object.entries(layerDisplayGroups).forEach((entry) => {
		  const [key, value] = entry;
		  map.addLayer(value);
		});
		
		map.addLayer(clusterGroup);
		
		var layerControl = L.control.layers(null, layerDisplayGroups, {"collapsed": false, "sortLayers": true} ).addTo(map);
		
		if (layerControl._layers. length == 0) {
			layerControl.remove();
		}

	}
	
	/* 	Location management adapted from:
		https://stackoverflow.com/questions/44757839/link-to-a-specific-point-on-leaflet-map 
		https://humanwhocodes.com/blog/2013/04/16/getting-the-url-of-an-iframes-parent		
	*/
	function getQueryStringValue (key) {  
		var isInIframe = (parent !== window),
			referenceSearch = null;

		// If this page is being used within an iFrame, consult the parent URL for the arguments. DEPRECATED (cross-origin error)
		if (isInIframe) {
			//const parentUrl = window.parent.location.href;
			//referenceSearch = parentUrl.split('?')[1];
			referenceSearch = window.location.search;		// Works only assuming parent page is responsible for passing the parameters(from wordpress, using advanced iframe plugin, for example)
		} else {
			referenceSearch = window.location.search;
		}
		
		const urlParams = new URLSearchParams(referenceSearch);
	
		console.log("isInIframe: " + isInIframe + ", Location search: " + referenceSearch + "; params: " + urlParams);	
		
		return urlParams.get(key) || 0;
	} 