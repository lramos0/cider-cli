# cider-cli
Cider-cli is a cli tool for producing CIDR maps, also known as "ip census maps", "ip maps", or "address space maps". These are very powerful graphs in your developer tool kit for understanding network traffic and visualizing address space in an organized fashion:
![example-map](https://raw.githubusercontent.com/lramos0/cider-cli/refs/heads/main/documentation/images/example-map.png )
The goal is to solve and visualize complexities in address spaces, trends which may be clearer simply with a little color:
![example-grouped-map](https://raw.githubusercontent.com/lramos0/cider-cli/refs/heads/main/documentation/images/example-grouped-map.png)

## Installation
Cider-cli is currently an unpublished tool, but for beta testing purposes you can install via:

### Install latest:
```shell
pip install cider-cli
```

### Development Installation

```shell
git clone https://github.com/lramos0/cider-cli
cd cider-cli
pip install -e .
```

## 🧭 How to Use?

You can produce CIDR maps on an input, see [supported data sources](#-supported-data-sources), using:
```shell
cider {input} --kind {geofeed|maxmind|pcap|cider} [options]

```

## 📁 Supported Data Sources
### 1. Formatted CSV (geofeeds, script outputs, etc)

CSV files with lines of the form:

ip_prefix,cc,region,city,...

Run:
```shell
cider ripe.csv --kind geofeed -o ripe_map.html
```

### 2. MaxMind CSV Snapshot Folder

The input must be the directory containing:

GeoLite2-City-Blocks-IPv4.csv
GeoLite2-City-Locations-en.csv

Run:
```shell
cider GeoLite2-City-CSV_20250902 --kind maxmind -o maxmind_map.html

```

### 3. Packet Capture (.pcap)

You can generate a quick pcap of outbound traffic:
```shell
sudo tcpdump -i en0 -w capture.pcap 'tcp[tcpflags] & tcp-syn != 0'
```

Visualize it:

ipmap map capture.pcap --kind pcap -o pcap_map.html

## 🎨 Visualization Options
Currently, the formats allow for the following options (default is html output). This can be set with the output tag:
```
--output result.html
--output result.png --output-format png
```

# 📊 Example: Full Command
```shell
cider ripe.20250903.geo.csv \
--kind geofeed \
--view /16 \
--mode primary \
--colorscale default \
--output ripe_map.html
```


## 🏁 Output

Every visualization is an interactive Plotly map with:

1. Clickable mode toggles

2. Primary org / country count / prefix count views

3. Responsive scaling

4. Exportable HTML or PNG