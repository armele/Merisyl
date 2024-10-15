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

        scale: function (zoom) {
            return Math.pow(2, zoom);
        },

        zoom: function (scale) {
            return Math.log(scale) / Math.LN2;
        },

        distance: function (latlng1, latlng2) {
            var dx = (latlng2.lng - latlng1.lng) * mapDim.metersPerPixel,
            dy = (latlng2.lat - latlng1.lat) * mapDim.metersPerPixel;

            return Math.sqrt(dx * dx + dy * dy);
        },
        infinite: true
    });

    //Creating the Map
    var map = L.map('map', {
        crs: L.CRS.pr,
        fullscreenControl: true,
    });

    var layerDisplayGroups = {}

    var mapBounds = new L.LatLngBounds(
            map.unproject([0, mapDim.referencesize], 8),
            map.unproject([mapDim.referencesize, 0], 8));
    map.setMaxBounds(mapBounds);

    var mapCenter = map.unproject([mapDim.referencesize / 2, mapDim.referencesize / 2], 8);

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

    L.control.scale({
        metric: true,
        maxWidth: 130
    }).addTo(map);
    initAjaxGeoJSON(layerDisplayGroups);

    for (var geoData in locationsList) {
        console.log("Loading: " + locationsList[geoData]);
        loadGeoJSON(locationsList[geoData], map); ;
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

function layerStyle(feature) {
    var default_style = {
        "color": "#eaeaea",
        "weight": ".3",
        "opacity": "0.0",
        "fillColor": "#eaeaea",
        "fillOpacity": "0.0"
    };
    var rewrite_keys = {
        'stroke': 'color',
        'stroke-width': 'weight',
        'stroke-opacity': 'opacity',
        'fill': 'fillColor',
        'fill-opacity': 'fillOpacity',
    };
    var props = feature.properties || {};
    var style = {};
    function camelFun(_, first_letter) {
        return first_letter.toUpperCase();
    };
    for (var key in props) {
        if (key.match('-')) {
            var camelcase = key.replace(/-(\w)/, camelFun);
            style[camelcase] = props[key];
        }
        // rewrite style keys from geojson.io
        if (rewrite_keys[key]) {
            style[rewrite_keys[key]] = props[key];
        }
    }
    return L.Util.extend(style, default_style);
}

function onEachFeature(feature, layer) {
    var props = feature.properties || {};
    var text = props["popup-text"] || "";
    if (text) {
        layer.bindPopup(text);
    }
}

function pointToLayer(feature, latlng) {
    var markerOptions = {}; // See https://leafletjs.com/reference.html#marker for options
    var props = feature.properties || {};
    var markerKey = props["marker-group"] || "";
    var customIconURL = customMarkers["Default"];

    if (customMarkers.hasOwnProperty(markerKey)) {
        customIconURL = customMarkers[markerKey];
    }

    var customIcon = L.icon({
        iconUrl: customIconURL,
        shadowUrl: 'https://pathfinder-gm-tools.s3.amazonaws.com/map/MerisylMapLocationMarkerShadow.png',

        iconSize: [30, 42], // size of the icon
        shadowSize: [26, 38], // size of the shadow
        iconAnchor: [15, 42], // point of the icon which will correspond to marker's location
        shadowAnchor: [02, 38], // the same for the shadow
        popupAnchor: [00, -20]// point from which the popup should open relative to the iconAnchor
    });

    if (useCustomMarkerIcon) {
        markerOptions["icon"] = customIcon;
    }

    return L.marker(latlng, markerOptions);
}

async function loadGeoJSON(targetfile, map) {
    return new Promise(resolve => {
        var layer = L.ajaxGeoJson(targetfile, {
            style: layerStyle,
            onEachFeature: onEachFeature,
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
    marker.on('dragend', function (e) {
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
                null, );
        layerDisplayGroups[key] = ldg;
        clusterGroup.addLayer(ldg);
    }

    return ldg;
}

function organizeClusters(map, layerDisplayGroups) {
    console.log("Organizing clusters.");
    // L.DomUtil.TRANSITION = true;

    var clusterGroup = L.markerClusterGroup({
        iconCreateFunction: function (cluster) {
            var markers = cluster.getAllChildMarkers();
            var html = '<div class="cluster">' + markers.length + '</div>';
            return L.divIcon({
                html: html,
                className: 'clusterIcon',
                iconSize: L.point(32, 32)
            });
        },
        spiderfyOnMaxZoom: false,
        showCoverageOnHover: true,
        zoomToBoundsOnClick: true,
        animate: false
    });

    map.eachLayer(function (layer) {
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

    var layerControl = L.control.layers(null, layerDisplayGroups, {
        "collapsed": false,
        "sortLayers": true
    }).addTo(map);

    if (layerControl._layers.length == 0) {
        layerControl.remove();
    }

}

/* 	Location management adapted from:
https://stackoverflow.com/questions/44757839/link-to-a-specific-point-on-leaflet-map
https://humanwhocodes.com/blog/2013/04/16/getting-the-url-of-an-iframes-parent
 */
function getQueryStringValue(key) {
    var isInIframe = (parent !== window),
    referenceSearch = null;

    // If this page is being used within an iFrame, consult the parent URL for the arguments. DEPRECATED (cross-origin error)
    if (isInIframe) {
        //const parentUrl = window.parent.location.href;
        //referenceSearch = parentUrl.split('?')[1];
        referenceSearch = window.location.search; // Works only assuming parent page is responsible for passing the parameters(from wordpress, using advanced iframe plugin, for example)
    } else {
        referenceSearch = window.location.search;
    }

    const urlParams = new URLSearchParams(referenceSearch);

    console.log("isInIframe: " + isInIframe + ", Location search: " + referenceSearch + "; params: " + urlParams);

    return urlParams.get(key) || 0;
}

/* Modified from:
https://cdn.jsdelivr.net/gh/gokertanrisever/leaflet-ruler@master/src/leaflet-ruler.js

to allow use of the custom CRS used on flat maps.
 */
(function (factory, window) {
    "use strict";
    if (typeof define === 'function' && define.amd) {
        define(['leaflet'], factory);
    } else if (typeof exports === 'object') {
        module.exports = factory(require('leaflet'));
    }
    if (typeof window !== 'undefined' && window.L) {
        window.L.Ruler = factory(L);
    }
}
    (function (L) {
        "use strict";
        L.Control.Ruler = L.Control.extend({
            options: {
                position: 'topright',
                events: {
                    onToggle: function (is_active) {}
                },
                circleMarker: {
                    color: 'red',
                    radius: 2
                },
                lineStyle: {
                    color: 'red',
                    dashArray: '1,6'
                },
                lengthUnit: {
                    display: 'm',
                    decimal: 2,
                    factor: null,
                    label: 'Distance:'
                },
                angleUnit: {
                    display: '&deg;',
                    decimal: 2,
                    factor: null,
                    label: 'Bearing:'
                }
            },
            isActive: function () {
                return this._choice;
            },
            onAdd: function (map) {
                this._map = map;
                this._container = L.DomUtil.create('div', 'leaflet-bar');
                this._container.classList.add('leaflet-ruler');
                L.DomEvent.disableClickPropagation(this._container);
                L.DomEvent.on(this._container, 'click', this._toggleMeasure, this);
                this._choice = false;
                this._defaultCursor = this._map._container.style.cursor;
                this._allLayers = L.layerGroup();
                return this._container;
            },
            onRemove: function () {
                L.DomEvent.off(this._container, 'click', this._toggleMeasure, this);
            },
            _toggleMeasure: function () {
                this._choice = !this._choice;
                this.options.events.onToggle(this._choice);
                this._clickedLatLong = null;
                this._clickedPoints = [];
                this._totalLength = 0;
                if (this._choice) {
                    this._map.doubleClickZoom.disable();
                    L.DomEvent.on(this._map._container, 'keydown', this._escape, this);
                    L.DomEvent.on(this._map._container, 'dblclick', this._closePath, this);
                    this._container.classList.add("leaflet-ruler-clicked");
                    this._clickCount = 0;
                    this._tempLine = L.featureGroup().addTo(this._allLayers);
                    this._tempPoint = L.featureGroup().addTo(this._allLayers);
                    this._pointLayer = L.featureGroup().addTo(this._allLayers);
                    this._polylineLayer = L.featureGroup().addTo(this._allLayers);
                    this._allLayers.addTo(this._map);
                    this._map._container.style.cursor = 'crosshair';
                    this._map.on('click', this._clicked, this);
                    this._map.on('mousemove', this._moving, this);
                } else {
                    this._map.doubleClickZoom.enable();
                    L.DomEvent.off(this._map._container, 'keydown', this._escape, this);
                    L.DomEvent.off(this._map._container, 'dblclick', this._closePath, this);
                    this._container.classList.remove("leaflet-ruler-clicked");
                    this._map.removeLayer(this._allLayers);
                    this._allLayers = L.layerGroup();
                    this._map._container.style.cursor = this._defaultCursor;
                    this._map.off('click', this._clicked, this);
                    this._map.off('mousemove', this._moving, this);
                }
            },
            _clicked: function (e) {
                this._clickedLatLong = e.latlng;
                this._clickedPoints.push(this._clickedLatLong);
                L.circleMarker(this._clickedLatLong, this.options.circleMarker).addTo(this._pointLayer);
                if (this._clickCount > 0 && !e.latlng.equals(this._clickedPoints[this._clickedPoints.length - 2])) {
                    if (this._movingLatLong) {
                        L.polyline([this._clickedPoints[this._clickCount - 1], this._movingLatLong], this.options.lineStyle).addTo(this._polylineLayer);
                    }
                    var text;
                    this._totalLength += this._result.Distance;
                    
					var distanceUnit = this.options.lengthUnit.display;
					var displayDistance;
					
					if (this._clickCount > 1) {
						displayDistance = this._totalLength.toFixed(this.options.lengthUnit.decimal)
					} else {
						displayDistance = this._result.Distance.toFixed(this.options.lengthUnit.decimal)
					}
					
					if (this._map.options.crs) {
						distanceUnit = "m";
						
						if (displayDistance > 10000) {
							distanceUnit = "km";
							displayDistance = (displayDistance/1000).toFixed(2);
						}
					}					
					
					// Removing broken bearing data for now...
					/*
                    text = '<b>' + this.options.angleUnit.label + '</b>&nbsp;' 
							+ this._result.Bearing.toFixed(this.options.angleUnit.decimal) + '&nbsp;' + this.options.angleUnit.display + '<br>'
							+ '<b>' + this.options.lengthUnit.label + '</b>&nbsp;' + displayDistance + '&nbsp;' + distanceUnit;
					*/
					text = '<b>' + this.options.lengthUnit.label + '</b>&nbsp;' + displayDistance + '&nbsp;' + distanceUnit;
							
                    L.circleMarker(this._clickedLatLong, this.options.circleMarker).bindTooltip(text, {
                        permanent: true,
                        className: 'result-tooltip'
                    }).addTo(this._pointLayer).openTooltip();
                }
                this._clickCount++;
            },
            _moving: function (e) {
                if (this._clickedLatLong) {
                    L.DomEvent.off(this._container, 'click', this._toggleMeasure, this);
                    this._movingLatLong = e.latlng;
                    if (this._tempLine) {
                        this._map.removeLayer(this._tempLine);
                        this._map.removeLayer(this._tempPoint);
                    }
                    var text;
                    this._addedLength = 0;
                    this._tempLine = L.featureGroup();
                    this._tempPoint = L.featureGroup();
                    this._tempLine.addTo(this._map);
                    this._tempPoint.addTo(this._map);
                    this._calculateBearingAndDistance();
                    this._addedLength = this._result.Distance + this._totalLength;
                    L.polyline([this._clickedLatLong, this._movingLatLong], this.options.lineStyle).addTo(this._tempLine);
					
                    if (this._clickCount > 1) {
                        // text = '<b>' + this.options.angleUnit.label + '</b>&nbsp;' + this._result.Bearing.toFixed(this.options.angleUnit.decimal) + '&nbsp;' + this.options.angleUnit.display + '<br><b>' + this.options.lengthUnit.label + '</b>&nbsp;' + this._addedLength.toFixed(this.options.lengthUnit.decimal) + '&nbsp;' + this.options.lengthUnit.display + '<br><div class="plus-length">(+' + this._result.Distance.toFixed(this.options.lengthUnit.decimal) + ')</div>';
                        text = '<b>' + this.options.lengthUnit.label + '</b>&nbsp;' + this._addedLength.toFixed(this.options.lengthUnit.decimal) + '&nbsp;' + this.options.lengthUnit.display + '<br><div class="plus-length">(+' + this._result.Distance.toFixed(this.options.lengthUnit.decimal) + ')</div>';						
						
                    } else {
                        // text = '<b>' + this.options.angleUnit.label + '</b>&nbsp;' + this._result.Bearing.toFixed(this.options.angleUnit.decimal) + '&nbsp;' + this.options.angleUnit.display + '<br><b>' + this.options.lengthUnit.label + '</b>&nbsp;' + this._result.Distance.toFixed(this.options.lengthUnit.decimal) + '&nbsp;' + this.options.lengthUnit.display;
                        text = '<b>' + this.options.lengthUnit.label + '</b>&nbsp;' + this._result.Distance.toFixed(this.options.lengthUnit.decimal) + '&nbsp;' + this.options.lengthUnit.display;						
                    }
                    L.circleMarker(this._movingLatLong, this.options.circleMarker).bindTooltip(text, {
                        sticky: true,
                        offset: L.point(0, -40),
                        className: 'moving-tooltip'
                    }).addTo(this._tempPoint).openTooltip();
                }
            },
            _escape: function (e) {
                if (e.keyCode === 27) {
                    if (this._clickCount > 0) {
                        this._closePath();
                    } else {
                        this._choice = true;
                        this._toggleMeasure();
                    }
                }
            },
			// TODO: Bearing doesn't work with flat map CRS.  I don't need it for now, so leaving it broken...
            _calculateBearingAndDistance: function () {
                var f1 = this._clickedLatLong.lat,
                l1 = this._clickedLatLong.lng,
                f2 = this._movingLatLong.lat,
                l2 = this._movingLatLong.lng;
                var toRadian = Math.PI / 180;
                // haversine formula
                // bearing
                var y = Math.sin((l2 - l1) * toRadian) * Math.cos(f2 * toRadian);
                var x = Math.cos(f1 * toRadian) * Math.sin(f2 * toRadian) - Math.sin(f1 * toRadian) * Math.cos(f2 * toRadian) * Math.cos((l2 - l1) * toRadian);
                var brng = Math.atan2(y, x) * ((this.options.angleUnit.factor ? this.options.angleUnit.factor / 2 : 180) / Math.PI);
                brng += brng < 0 ? (this.options.angleUnit.factor ? this.options.angleUnit.factor : 360) : 0;

                // distance
                var distance;
                if (this._map.options.crs) {
                    // Added below to use CRS distance calc
                    // distance = this._map.options.crs.distance(this._map.project(this._clickedLatLong), this._map.project(this._movingLatLong))
					distance = this._map.options.crs.distance(this._clickedLatLong, this._movingLatLong)
                } else {
                    var R = this.options.lengthUnit.factor ? 6371 * this.options.lengthUnit.factor : 6371; // kilometres
                    var deltaF = (f2 - f1) * toRadian;
                    var deltaL = (l2 - l1) * toRadian;
                    var a = Math.sin(deltaF / 2) * Math.sin(deltaF / 2) + Math.cos(f1 * toRadian) * Math.cos(f2 * toRadian) * Math.sin(deltaL / 2) * Math.sin(deltaL / 2);
                    var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
                    distance = R * c;
                }

                this._result = {
                    Bearing: brng,
                    Distance: distance
                };
            },
            _closePath: function () {
                this._map.removeLayer(this._tempLine);
                this._map.removeLayer(this._tempPoint);
                if (this._clickCount <= 1)
                    this._map.removeLayer(this._pointLayer);
                this._choice = false;
                L.DomEvent.on(this._container, 'click', this._toggleMeasure, this);
                this._toggleMeasure();
            }
        });
        L.control.ruler = function (options) {
            return new L.Control.Ruler(options);
        };
    }, window));
