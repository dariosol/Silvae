const API_BASE = "http://127.0.0.1:5000";  // Flask Backend

let map;
let markers = [];

// Load cities on page load
window.onload = () => {
    fetch(`${API_BASE}/cities`)
        .then(res => res.json())
        .then(data => {
            const citySelect = document.getElementById("citySelect");
            data.forEach(city => {
                const option = document.createElement("option");
                option.value = city;
                option.textContent = city;
                citySelect.appendChild(option);
            });
        });
};

// 📍 Autofill latitude/longitude with GPS
function getLocation() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                document.getElementById("latitude").value = position.coords.latitude;
                document.getElementById("longitude").value = position.coords.longitude;
            },
            (error) => {
                document.getElementById("status").innerText = "Error getting location: " + error.message;
            }
        );
    } else {
        document.getElementById("status").innerText = "Geolocation is not supported by this browser.";
    }
}

// Fetch streets based on city
function fetchStreets() {
    let city = document.getElementById("citySelect").value;
    if (!city) return;

    fetch(`${API_BASE}/streets/${city}`)
        .then(res => res.json())
        .then(data => {
            let streetSelect = document.getElementById("streetSelect");
            streetSelect.innerHTML = `<option value="">-- Choose a street --</option>`;
            data.forEach(street => {
                let option = document.createElement("option");
                option.value = street;
                option.textContent = street;
                streetSelect.appendChild(option);
            });
        });
}

// Fetch trees with optional filters
function fetchTrees() {
    const city = document.getElementById("citySelect").value;
    const addressPart = document.getElementById("streetSearch").value.trim();

    let url = `${API_BASE}/trees?city=${encodeURIComponent(city)}`;
    if (addressPart) url += `&address=${encodeURIComponent(addressPart)}`;

    fetch(url)
        .then(res => res.json())
        .then(data => {
            const tableBody = document.getElementById("treeList");
            tableBody.innerHTML = "";

            data.forEach(tree => {
                const row = `
                    <tr>
                        <td>${tree.id}</td>
                        <td>${tree.custom_id}</td>
                        <td>${tree.species}</td>
                        <td>${tree.condition}</td>
                        <td>${tree.address}</td>
                        <td><button class="btn btn-warning btn-sm" onclick="editTree(${tree.id})">Edit</button></td>
                        <td><button class="btn btn-primary btn-sm" onclick="viewTreeDetails(${tree.id})">View Details</button></td>
                        <td><button class="btn btn-danger btn-sm" onclick="deleteTreeById(${tree.id})">Delete</button></td>
                    </tr>`;
                tableBody.innerHTML += row;
            });
        });
}

// Find tree by custom ID
function fetchTreeById() {
    let customId = document.getElementById("treeIdInput").value;
    if (!customId) return alert("Please enter a Custom ID");

    fetch(`${API_BASE}/tree/custom/${customId}`)
        .then(res => res.json())
        .then(data => {
            if (data.message) {
                alert("Tree not found!");
                return;
            }
            alert(`Tree Found:\nSpecies: ${data.species}\nCondition: ${data.condition}\nComments: ${data.comments}`);
        })
        .catch(() => alert("Tree not found"));
}

// View details popup
function viewTreeDetails(treeId) {
    fetch(`${API_BASE}/tree/${treeId}`)
        .then(res => res.json())
        .then(tree => {
            alert(`
Tree Details:
Species: ${tree.species}
Condition: ${tree.condition}
Height: ${tree.height}
Trunk Diameter: ${tree.trunk_diameter_cm} cm
Crown Diameter: ${tree.crown_diameter_m} m
Age: ${tree.age}
Actions: ${tree.actions}
Location: ${tree.location}
CPC: ${tree.cpc}
Next Check: ${tree.next_check}
Comments: ${tree.comments}
            `);
        })
        .catch(() => alert("Tree not found"));
}

// Switch to edit mode and pre-fill form
function editTree(treeId) {
    fetch(`${API_BASE}/tree/${treeId}`)
        .then(res => res.json())
        .then(tree => {
            document.getElementById("editTreeId").value = tree.id;
            document.getElementById("formTitle").innerText = "✍️ Edit Tree";
            document.getElementById("formSubmitButton").innerText = "💾 Save Changes";

            Object.keys(tree).forEach(field => {
                const input = document.getElementById(field);
                if (input) input.value = tree[field] || "";
            });

            window.scrollTo({ top: 0, behavior: 'smooth' });
        })
        .catch(() => alert("Error loading tree for editing."));
}

// Handle add or edit submission
document.getElementById("addTreeForm").addEventListener("submit", function(event) {
    event.preventDefault();

    const treeId = document.getElementById("editTreeId").value;

    const treeData = {
        custom_id: document.getElementById("custom_id").value.trim(),
        city: document.getElementById("city").value.trim(),
        address: document.getElementById("address").value.trim(),
        latitude: parseFloat(document.getElementById("latitude").value) || null,
        longitude: parseFloat(document.getElementById("longitude").value) || null,
        species: document.getElementById("species").value.trim(),
        condition: document.getElementById("condition").value.trim(),
        comments: document.getElementById("comments").value.trim(),
        height: document.getElementById("height").value.trim(),
        trunk_diameter_cm: parseFloat(document.getElementById("trunk_diameter_cm").value) || null,
        crown_diameter_m: parseFloat(document.getElementById("crown_diameter_m").value) || null,
        age: document.getElementById("age").value.trim(),
        actions: document.getElementById("actions").value.trim(),
        location: document.getElementById("location").value.trim(),
        cpc: document.getElementById("cpc").value.trim(),
        next_check: document.getElementById("next_check").value || null
    };

    if (!treeData.custom_id || !treeData.city || !treeData.species || !treeData.condition) {
        alert("Custom ID, City, Species, and Condition are required.");
        return;
    }

    const url = treeId ? `${API_BASE}/tree/${treeId}` : `${API_BASE}/add_tree`;
    const method = treeId ? "PATCH" : "POST";

    fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(treeData)
    })
    .then(res => res.json())
    .then(data => {
        alert(data.message);
        resetForm();
        fetchTrees();
    })
    .catch(error => console.error("Error saving tree:", error));
});

// Reset form to add mode
function resetForm() {
    document.getElementById("addTreeForm").reset();
    document.getElementById("editTreeId").value = "";
    document.getElementById("formTitle").innerText = "🌳 Add a New Tree";
    document.getElementById("formSubmitButton").innerText = "🌳 Add Tree";
}

// Delete tree
function deleteTreeById(treeId) {
    if (!confirm("Are you sure you want to delete this tree?")) return;

    fetch(`${API_BASE}/tree/${treeId}`, { method: "DELETE" })
        .then(res => res.json())
        .then(data => {
            alert(data.message);
            fetchTrees();
        })
        .catch(error => console.error("Error deleting tree:", error));
}

// Toggle map view
function toggleMap() {
    let mapDiv = document.getElementById("map");
    if (mapDiv.style.display === "none") {
        mapDiv.style.display = "block";
        if (!map) {
            map = L.map("map").setView([45.07, 7.69], 13);
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(map);
        }
        fetchTreesOnMap();
    } else {
        mapDiv.style.display = "none";
    }
}

// Show trees on map
function fetchTreesOnMap() {
    let city = document.getElementById("citySelect").value;
    let addressPart = document.getElementById("streetSearch").value.trim();

    let url = `${API_BASE}/trees?city=${encodeURIComponent(city)}`;
    if (addressPart) url += `&address=${encodeURIComponent(addressPart)}`;

    fetch(url)
        .then(res => res.json())
        .then(data => {
            markers.forEach(marker => map.removeLayer(marker));
            markers = [];

            if (data.length === 0) {
                alert("No trees found for the selected filters.");
                return;
            }

            data.forEach(tree => {
                if (!tree.latitude || !tree.longitude) return;
                let marker = L.marker([tree.latitude, tree.longitude])
                    .bindPopup(`
                        <b>Species:</b> ${tree.species}<br>
                        <b>Condition:</b> ${tree.condition}<br>
                        <b>Address:</b> ${tree.address}<br>
                        <b>Next Check:</b> ${tree.next_check || "N/A"}
                    `);
                marker.addTo(map);
                markers.push(marker);
            });

            const firstTree = data[0];
            if (firstTree && firstTree.latitude && firstTree.longitude) {
                map.setView([firstTree.latitude, firstTree.longitude], 15);
            }
        })
        .catch(error => console.error("Error fetching trees for map:", error));
}
