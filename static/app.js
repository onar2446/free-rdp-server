(function(){
	const form = document.getElementById('teacher-form');
	const useLocBtn = document.getElementById('use-location');
	const latEl = document.getElementById('lat');
	const lonEl = document.getElementById('lon');
	const locStatus = document.getElementById('loc-status');

	if (useLocBtn) {
		useLocBtn.addEventListener('click', function(){
			if (!navigator.geolocation) {
				locStatus.textContent = 'المتصفح لا يدعم تحديد الموقع';
				return;
			}
			locStatus.textContent = 'جارِ تحديد الموقع...';
			navigator.geolocation.getCurrentPosition(function(pos){
				latEl.value = String(pos.coords.latitude);
				lonEl.value = String(pos.coords.longitude);
				locStatus.textContent = 'تم تحديد الموقع';
			}, function(err){
				console.error(err);
				locStatus.textContent = 'تعذّر تحديد الموقع';
			}, {enableHighAccuracy:true, timeout:10000, maximumAge:0});
		});
	}

	if (window.SEARCH_DATA) {
		const data = window.SEARCH_DATA;
		const map = L.map('map');
		const center = [data.center.lat, data.center.lon];
		map.setView(center, 14);
		L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
			maxZoom: 19,
			attribution: '&copy; OpenStreetMap'
		}).addTo(map);

		const teacherIcon = L.icon({
			iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
			iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
			shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
			iconSize: [25, 41],
			iconAnchor: [12, 41],
			popupAnchor: [1, -34],
			shadowSize: [41, 41]
		});

		L.marker(center, {icon: teacherIcon}).addTo(map).bindPopup('موقعك');
		const radiusMeters = (data.radius_km || 5) * 1000;
		L.circle(center, {radius: radiusMeters, color: '#2563eb', weight: 1}).addTo(map);

		const list = document.querySelector('.results');
		list.innerHTML = '';

		const bounds = L.latLngBounds(center, center);
		(data.schools || []).forEach(function(s, idx){
			const item = document.createElement('li');
			item.className = 'result-item';
			const title = document.createElement('div');
			title.innerHTML = `<strong>${s.name || 'مدرسة'}</strong> <span class="badge">${s.distance_km} كم</span>`;
			const addr = document.createElement('div');
			addr.className = 'muted';
			addr.textContent = s.address || '';
			item.appendChild(title);
			item.appendChild(addr);
			list.appendChild(item);

			const marker = L.marker([s.lat, s.lon]).addTo(map);
			marker.bindPopup(`${s.name || 'مدرسة'}<br/>${s.address || ''}<br/>المسافة: ${s.distance_km} كم`);
			bounds.extend([s.lat, s.lon]);
		});

		if ((data.schools || []).length > 0) {
			map.fitBounds(bounds.pad(0.2));
		}
	}
})();