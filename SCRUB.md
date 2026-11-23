# Scrubbing record

This repository is the public documentation archive of the LibreEcho port to the Echo Plus
2nd Gen (device codename Lidar): the plan, the workspace notes and the phase experiment
records. It holds text only. Device images, audio recordings, packet captures and key
material stay in the private workspace. The notes also name workspace paths (`dumps/`,
`artifacts/`, `repos/`, `reference/`, `mtkclient/`); these are locations in that private
workspace, not directories in this repository.

## What was left out

- `dumps/`, `artifacts/` (except the small manifests already quoted in notes), `repos/`,
  `reference/` and the `mtkclient/` checkout.
- Device images and binaries: `.bin`, `.dtb`, `.img`, `.elf`, `.ko`, object files, shared
  libraries, archives, packages and firmware blobs. Python caches were also dropped.
- Microphone and audio captures: `.wav`, `.pcm` and `.mp3`. This also covers the Sendspin
  silence experiment (`experiments/phase-07/sendspin-silence/`): audio probes, the `repro`
  and `fifo_semantics` binaries, and the copied audio engine test build.
- The stock 2018 boot log (`experiments/phase-01/dtb/boot-log-2018-08-22.txt`). Only short
  quotes remain in the notes.
- The two Wi-Fi scan dumps from the API sweep
  (`step33-gap-checks/ApiSweep/api/get_network_wifi_scan.json` and `ws_wifi_scan.json`).
  They list every network visible from the lab.
- The host USB device inventory, which lists workstation hardware and serial numbers.
- Lab housekeeping scripts such as `push-to-forks.sh` and `delete-old-branches.sh`. They
  name the owner's remotes and are of no use outside the lab.
- Vendored or generated trees: toolchains, Python virtual environments, extracted sysroots,
  kernel and mbedTLS build outputs, and captured session state.
- Raw LAN discovery dumps (`mdns-browse-*.log`). They list third-party devices, IPv6
  addresses, Matter node and fabric identifiers, and network names beyond the Lidar unit.
- Raw strings and hexdumps extracted from stock boot images (`boot0_strings.txt`,
  `lk_strings.txt`, `lk_probe.txt`, `lk_window.txt`). They carry image key material and
  device-unique values.
- Any text file larger than 1.5 MB. In practice this drops bulk build logs and keeps the
  phase notes and the command output that documents results.
- The pstore dump `experiments/phase-05/hw-20261118/step4-noboot/ramoops.txt`. Its text is
  corrupted by flipped bits throughout, so pattern scans could not clear it reliably, and
  fragments of the unlock token and a partition GUID were still readable. No note cites it.

## Placeholders

Device and owner values were replaced with stable placeholders: the same real value always
maps to the same placeholder, so logs can still be compared with each other. A suffix of
`_n` stands for a numbered series (`<PARTUUID_1>`, `<PARTUUID_2>`, ...). The real values
are kept in the private workspace, not in this repository.

### Device identity

| Placeholder | Meaning |
| --- | --- |
| `<SERIAL_A>` | Device serial number, also used as the adb serial |
| `<ME_ID_A>` | Device management identifier |
| `<EMMC_CID_A>` | eMMC CID register value |
| `<EFUSE_n>` | eFuse words read from the SoC |
| `<LED_CALIB_A>` | LED calibration value from the factory data |
| `<PARTUUID_n>` | eMMC partition GUIDs, numbered in GPT order |
| `<FS_UUID_n>` | ext4 filesystem UUIDs |
| `<TU_CODE>`, `<UNLOCK_CODE>` | Per-device fastboot unlock tokens |

### Network and radio

| Placeholder | Meaning |
| --- | --- |
| `<SSID_A>`, `<SSID_B>` | Owner Wi-Fi networks |
| `<MAC_WLAN_A>`, `<MAC_WLAN_ALT_A>`, `<MAC_AP_A>`, `<MAC_AP0_A>`, `<MAC_P2P_A>` | Device radio MAC addresses |
| `<MAC_WLAN_A_COMPACT>` | The WLAN MAC without separators, as AirPlay (RAOP) advertises it |
| `<MAC_GADGET_HOST_n>`, `<MAC_GADGET_DEV_n>` | USB gadget network MAC pairs |
| `<MAC_BT_PEER_A>`, `<BT_PEER_NAME_A>` | Owner phone Bluetooth address and name |
| `<DEVICE_IP_A>`, `<LAN_GATEWAY_A>`, `<LAN_GATEWAY_B>`, `<LAN_NET_B>`, `<LAN_CIDR_A>`, `<LAN_HOST_A_n>`, `<LAN_HOST_B_n>`, `<CLUSTER_IP_n>`, `<SETUP_AP_IP_A>`, `<SETUP_AP_HOST_A>` | IPv4 LAN addresses |
| `<ULA_ADDRESS_A>`, `<LINK_LOCAL_IPV6_A>`, `<THREAD_ULA_A>` | IPv6 LAN addresses |
| `<THREAD_PANID_A>`, `<THREAD_XPANID_A>`, `<THREAD_EXTADDR_A>` | PAN ID, extended PAN ID and node address of the test Thread network |

### Pairing and API secrets

| Placeholder | Meaning |
| --- | --- |
| `<ZB_NETWORK_KEY>`, `<ZB_PRECONFIGURED_KEY>` | ZigBee key material |
| `<ESPHOME_NOISE_KEY_A>` | ESPHome Noise protocol pre-shared key |
| `<ESPHOME_KEYPAIR_A>` | Sendspin persistent keypair |
| `<ESPHOME_PAIR_CONFIG_A>`, `<ESPHOME_PSK_A>` | Pairing configuration and pre-shared key |
| `<TOKEN>` | Bearer and CSRF tokens in API logs |
| `<WEB_USER_A>`, `<WEB_SALT_A>`, `<WEB_HASH_A>` | Owner account name, salt and password hash in the device web UI users file |
| `<WEB_SALT_n>`, `<WEB_HASH_n>` | Salts and hashes of the temporary test accounts (`le-sweep22` and similar) |

Lab API passwords were removed from scripts; they now read `LIBREECHO_WEB_PASSWORD` from the
environment.

### Owner environment

| Placeholder | Meaning |
| --- | --- |
| `<WORKSTATION_A>` | Build host name |
| `/workspace/libreecho`, `/home/build` | Workstation paths |
| `<HA_HOST_A>`, `<HOME_DOMAIN_A>` | Owner Home Assistant URL and home domain |
| `<HA_ENTITY_A>`, `<HA_ENTITY_B>`, `<MA_PLAYER_A>` | Home Assistant and Music Assistant player names |
| `<ROOM_A>` | Room name |
| `<PCAP_FILE_A>`, `<PCAP_FILE_B>` | File names of packet captures taken in the owner's home |
| `<K8S_NODE_A>`, `<K8S_NAMESPACE_A>`, `<HA_POD_A>`, `<MA_POD_A>`, `<NETATTACH_A>`, `<BRIDGE_A>`, `<CILIUM_IFACE_A>` | Lab Kubernetes node, namespace, pod, network attachment, bridge and interface names |

## What was kept on purpose

These values stay because they identify no one:

- MAC sentinels and examples: `ff:ff:ff:ff:ff:ff`, `00:00:00:00:00:00`,
  `11:22:33:44:55:66`.
- IPv4 wildcard, loopback, multicast and link-local addresses: `0.0.0.0`, `127.0.0.1`,
  `224.0.0.251`, and the two `169.254.x.x` USB link-local addresses.
- The Linux filesystem partition type GUID `0FC63DAF-8483-4772-8E79-3D69D8477DE4`, which is
  a published constant.
- Kernel `boot_id` values. Each one is random and new on every boot; the notes use them to
  prove that a reboot happened.
- The USB gadget serial `LIDAR0001`, a fixed string set by our own bring-up images.
- Timestamps in AEDT (+1100) and the `en_AU` locale. They show the lab is in Australia and
  nothing narrower.
- Vendor build host names in stock firmware logs, and the public maintainer email addresses
  in those logs.

## Caveats

A line that used to show a serial number or an address now shows the placeholder name, so
some experiment commands that embedded a LAN address will not run unchanged. The repository
records evidence; it is not a runnable lab snapshot.

## Final scan

Before publishing, a checker in the private workspace scans every text file for each
removed value, for the partition and filesystem UUIDs, and for generic patterns: MAC
addresses, private IPv4 ranges, IPv6 ULA and link-local addresses, fastboot tokens, serial
number fields, base64 keys and workstation paths. The checker stays private because it lists
the real values it looks for. The last run on this snapshot reported:

```
scanned 1240 text files, hits=0
```
