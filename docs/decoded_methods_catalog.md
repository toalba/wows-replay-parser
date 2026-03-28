# Decoded Entity Methods Catalog

Generated: 2026-03-28 19:16

**Replays parsed:** 1
**Total packets:** 163,757
**Entity method packets:** 37,309
**Unique (entity.method) combos:** 77

## Non-Method Packets of Interest

- **PlayerOrientation (0x2C)**: 15,776 packets, payload sizes: [32, 32, 32, 32, 32]
- **Position (0x0A)**: 24,585 packets, payload sizes: [45, 45, 45, 45, 45]

## Summary Table

| Entity.Method | Calls | Decoded | Failed | Fields |
|---|---|---|---|---|
| `Avatar.activateAirSupport` | 8 | 8 | 0 | index, squadronID, position, aimLength, airSupportShotID |
| `Avatar.beginOwnerlessTracers` | 49 | 49 | 0 | arg0, arg1, arg2 |
| `Avatar.changePreBattleGrants` | 1 | 1 | 0 | grants |
| `Avatar.deactivateAirSupport` | 8 | 8 | 0 | index, squadronID |
| `Avatar.endOwnerlessTracers` | 49 | 49 | 0 | arg0, arg1, arg2 |
| `Avatar.onAchievementEarned` | 4 | 4 | 0 | arg0, arg1 |
| `Avatar.onArenaStateReceived` | 1 | 1 | 0 | arenaUniqueId, teamBuildTypeId, preBattlesInfo, playersSt... |
| `Avatar.onBattleEnd` | 1 | 1 | 0 | (none) |
| `Avatar.onChatMessage` | 37 | 35 | 2 | arg0, arg1, arg2, arg3 |
| `Avatar.onConnected` | 1 | 1 | 0 | artilleryAmmoId, torpdoAmmoId, airSupportAmmoId, torpedoS... |
| `Avatar.onEnterPreBattle` | 1 | 1 | 0 | packedPreBattleData, grants, isRecreated |
| `Avatar.onGameRoomStateChanged` | 88 | 88 | 0 | playersData, botsData, observersData |
| `Avatar.onOwnerChanged` | 1 | 1 | 0 | ownerId, isOwner |
| `Avatar.onShutdownTime` | 1 | 1 | 0 | arg0, arg1, arg2 |
| `Avatar.onWorldStateReceived` | 1 | 1 | 0 | (none) |
| `Avatar.receiveArtilleryShots` | 2590 | 2590 | 0 | arg0 |
| `Avatar.receiveAvatarInfo` | 1 | 1 | 0 | arg0 |
| `Avatar.receiveChatHistory` | 1 | 1 | 0 | arg0 |
| `Avatar.receiveDamageStat` | 152 | 152 | 0 | arg0 |
| `Avatar.receiveDepthChargesPacks` | 2 | 2 | 0 | arg0 |
| `Avatar.receiveExplosions` | 64 | 64 | 0 | arg0 |
| `Avatar.receivePlaneProjectilePack` | 156 | 156 | 0 | arg0 |
| `Avatar.receivePlayerData` | 2 | 2 | 0 | arg0, arg1 |
| `Avatar.receiveShellInfo` | 279 | 279 | 0 | arg0, arg1, arg2, arg3, arg4, arg5, arg6, arg7, arg8, arg... |
| `Avatar.receiveShotKills` | 1583 | 1583 | 0 | arg0 |
| `Avatar.receiveTorpedoArmed` | 142 | 142 | 0 | arg0, arg1 |
| `Avatar.receiveTorpedoSynchronization` | 291 | 291 | 0 | ownerID, shotID, serverPos |
| `Avatar.receiveTorpedoes` | 178 | 178 | 0 | arg0 |
| `Avatar.receiveVehicleDeath` | 20 | 20 | 0 | arg0, arg1, arg2 |
| `Avatar.receive_CommonCMD` | 35 | 35 | 0 | playerId, command |
| `Avatar.receive_addMinimapSquadron` | 11 | 11 | 0 | arg0, arg1, arg2, arg3, arg4 |
| `Avatar.receive_addSquadron` | 11 | 11 | 0 | arg0, arg1, arg2, arg3, arg4, arg5, arg6 |
| `Avatar.receive_changeState` | 31 | 31 | 0 | arg0, arg1, arg2 |
| `Avatar.receive_deactivateSquadron` | 10 | 10 | 0 | arg0, arg1 |
| `Avatar.receive_planeDeath` | 26 | 26 | 0 | arg0, arg1, arg2, arg3 |
| `Avatar.receive_refresh` | 1 | 1 | 0 | arg0 |
| `Avatar.receive_removeMinimapSquadron` | 11 | 11 | 0 | arg0 |
| `Avatar.receive_removeSquadron` | 11 | 11 | 0 | arg0 |
| `Avatar.receive_resetWaypoints` | 122 | 122 | 0 | arg0, arg1 |
| `Avatar.receive_squadronHealth` | 392 | 392 | 0 | arg0, arg1 |
| `Avatar.receive_squadronPlanesHealth` | 94 | 94 | 0 | arg0, arg1 |
| `Avatar.receive_squadronVisibilityChanged` | 16 | 16 | 0 | arg0, arg1 |
| `Avatar.receive_stopManeuvering` | 10 | 10 | 0 | squadronId |
| `Avatar.receive_updateMinimapSquadron` | 170 | 170 | 0 | arg0, arg1 |
| `Avatar.receive_updateSquadron` | 308 | 308 | 0 | arg0, arg1, arg2 |
| `Avatar.startDissapearing` | 97 | 97 | 0 | arg0 |
| `Avatar.updateCoolDown` | 11 | 11 | 0 | arg0 |
| `Avatar.updateMinimapVisionInfo` | 1938 | 1938 | 0 | arg0, arg1 |
| `Avatar.updateOwnerlessAuraState` | 77 | 77 | 0 | arg0, arg1, arg2, arg3 |
| `Avatar.updateOwnerlessTracersPosition` | 407 | 407 | 0 | arg0, arg1, arg2 |
| `Avatar.updatePreBattlesInfo` | 22 | 22 | 0 | packedData |
| `Vehicle.kill` | 20 | 20 | 0 | arg0, arg1, arg2, arg3, arg4, arg5, arg6, arg7, arg8 |
| `Vehicle.makeShipCracksActive` | 18 | 18 | 0 | (none) |
| `Vehicle.onConsumableInterrupted` | 1 | 1 | 0 | arg0 |
| `Vehicle.onConsumableUsed` | 102 | 102 | 0 | consumableUsageParams, workTimeLeft |
| `Vehicle.onCrashCrewDisable` | 4 | 4 | 0 | (none) |
| `Vehicle.onCrashCrewEnable` | 4 | 4 | 0 | (none) |
| `Vehicle.onPrioritySectorSet` | 7 | 7 | 0 | arg0, arg1 |
| `Vehicle.onWeaponStateSwitched` | 2 | 2 | 0 | arg0, arg1 |
| `Vehicle.receiveDamagesOnShip` | 1161 | 1161 | 0 | arg0 |
| `Vehicle.receiveGunSyncRotations` | 18 | 18 | 0 | arg0, arg1 |
| `Vehicle.receiveHitLocationStateChange` | 2922 | 2922 | 0 | arg0, arg1 |
| `Vehicle.receiveHitLocationsInitialState` | 100 | 100 | 0 | arg0, arg1 |
| `Vehicle.resetResettableWaveEnemyHits` | 4 | 4 | 0 | (none) |
| `Vehicle.setAirDefenseState` | 1 | 1 | 0 | arg0 |
| `Vehicle.setAmmoForWeapon` | 43 | 43 | 0 | weaponType, ammoParamsId, isReload |
| `Vehicle.setConsumables` | 100 | 100 | 0 | arg0 |
| `Vehicle.setReloadingStateForWeapon` | 5 | 5 | 0 | arg0, arg1 |
| `Vehicle.setUniqueSkills` | 1 | 1 | 0 | arg0 |
| `Vehicle.shootATBAGuns` | 888 | 888 | 0 | arg0 |
| `Vehicle.shootOnClient` | 1173 | 1173 | 0 | arg0, arg1 |
| `Vehicle.shootTorpedo` | 46 | 46 | 0 | arg0, arg1, arg2, arg3, arg4 |
| `Vehicle.syncGun` | 450 | 450 | 0 | weaponType, gunId, yaw, pitch, alive, reloadPerc, loadedAmmo |
| `Vehicle.syncShipPhysics` | 100 | 100 | 0 | arg0, arg1 |
| `Vehicle.syncTorpedoState` | 100 | 100 | 0 | arg0 |
| `Vehicle.syncTorpedoTube` | 70 | 70 | 0 | arg0, arg1, arg2, arg3, arg4, arg5 |
| `Vehicle.uniqueTriggerActivated` | 3 | 3 | 0 | (none) |

## 1. Ship Positions / Movement

### `Avatar.updateOwnerlessTracersPosition`

- **Calls:** 407 | **Decoded:** 407 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
  - `arg2`: `Container`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 1041031
  arg1: 0
  arg2: Container(x=240.4293670654297, y=2.609792947769165, z=255.54542541503906)
  ```

  **Example 2:**
  ```
  arg0: 1041031
  arg1: 2
  arg2: Container(x=232.28485107421875, y=2.609792947769165, z=233.1865997314453)
  ```

  **Example 3:**
  ```
  arg0: 1041031
  arg1: 3
  arg2: Container(x=237.1016387939453, y=2.609792947769165, z=232.7858428955078)
  ```

### `Vehicle.syncShipPhysics`

- **Calls:** 100 | **Decoded:** 100 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `bytes`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: -1
  arg1: b'\x80\x02J\xff\xff\xff\xffUX\xcd\xcc\xcc=v\x86\x06\xc4\x00\x00\x00\x00\xff\xff\...
  ```

  **Example 2:**
  ```
  arg0: -1
  arg1: b'\x80\x02J\xff\xff\xff\xffUX\xcd\xcc\xcc=`b\x04\xc6\x00\x00\x00\x00\xff\xff\xe0...
  ```

  **Example 3:**
  ```
  arg0: -1
  arg1: b'\x80\x02J\xff\xff\xff\xffUX\xcd\xcc\xcc=S\xdb\xfaE\x00\x00\x00\x00\xff\xef\xd2...
  ```

## 2. Combat Events

### `Avatar.receiveArtilleryShots`

- **Calls:** 2,590 | **Decoded:** 2,590 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `ListContainer`
- **Suspicious values:**
  - arg0[].paramsID: very large: 4159685424
  - arg0[].paramsID: very large: 4173316912
  - arg0[].paramsID: very large: 4171219664
  - arg0[].paramsID: very large: 4193239504
  - arg0[].paramsID: very large: 4277126096
- **Examples (3):**

  **Example 1:**
  ```
  arg0: ListContainer([Container(paramsID=4159685424, ownerID=1041039, salvoID=0, shots=...
  ```

  **Example 2:**
  ```
  arg0: ListContainer([Container(paramsID=4159685424, ownerID=1041039, salvoID=1, shots=...
  ```

  **Example 3:**
  ```
  arg0: ListContainer([Container(paramsID=4159685424, ownerID=1041039, salvoID=2, shots=...
  ```

### `Avatar.receiveDamageStat`

- **Calls:** 152 | **Decoded:** 152 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `bytes`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: b'\x80\x02}q\x01K\x01K\x00\x86q\x02]q\x03(K\x04G@\xacM\x00\x00\x00\x00\x00es.'
  ```

  **Example 2:**
  ```
  arg0: b'\x80\x02}q\x01K\x02K\x00\x86q\x02]q\x03(K\x03G@\xa8\xc0\x00\x00\x00\x00\x00es....
  ```

  **Example 3:**
  ```
  arg0: b'\x80\x02}q\x01K\x02K\x00\x86q\x02]q\x03(K\x06G@\xb8\xc0\x00\x00\x00\x00\x00es....
  ```

### `Avatar.receiveDepthChargesPacks`

- **Calls:** 2 | **Decoded:** 2 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `ListContainer`
- **Suspicious values:**
  - arg0[].paramsID: very large: 4182655984
- **Examples (2):**

  **Example 1:**
  ```
  arg0: ListContainer([Container(ownerID=1041051, salvoID=0, paramsID=4182655984, depthC...
  ```

  **Example 2:**
  ```
  arg0: ListContainer([Container(ownerID=1041051, salvoID=0, paramsID=4182655984, depthC...
  ```

### `Avatar.receiveShotKills`

- **Calls:** 1,583 | **Decoded:** 1,583 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `ListContainer`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: ListContainer([Container(ownerID=1041025, hitType=97, kills=ListContainer([Conta...
  ```

  **Example 2:**
  ```
  arg0: ListContainer([Container(ownerID=1041045, hitType=64, kills=ListContainer([Conta...
  ```

  **Example 3:**
  ```
  arg0: ListContainer([Container(ownerID=1041009, hitType=64, kills=ListContainer([Conta...
  ```

### `Avatar.receiveTorpedoArmed`

- **Calls:** 142 | **Decoded:** 142 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 1041047
  arg1: 1
  ```

  **Example 2:**
  ```
  arg0: 1041047
  arg1: 2
  ```

  **Example 3:**
  ```
  arg0: 1041047
  arg1: 3
  ```

### `Avatar.receiveTorpedoSynchronization`

- **Calls:** 291 | **Decoded:** 291 (100.0%) | **Failed:** 0
- **Fields:**
  - `ownerID`: `int`
  - `shotID`: `int`
  - `serverPos`: `Container`
- **Examples (3):**

  **Example 1:**
  ```
  ownerID: 1041047
  shotID: 5
  serverPos: Container(x=401.439453125, y=-0.14000000059604645, z=-249.58526611328125)
  ```

  **Example 2:**
  ```
  ownerID: 1041047
  shotID: 1
  serverPos: Container(x=391.93719482421875, y=-0.14000000059604645, z=-233.62229919433594)
  ```

  **Example 3:**
  ```
  ownerID: 1041047
  shotID: 2
  serverPos: Container(x=391.3955383300781, y=-0.14000000059604645, z=-233.96205139160156)
  ```

### `Avatar.receiveTorpedoes`

- **Calls:** 178 | **Decoded:** 178 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `ListContainer`
- **Suspicious values:**
  - arg0[].paramsID: very large: 4170597200
  - arg0[].skinID: very large: 3550361424
  - arg0[].paramsID: very large: 4234560304
  - arg0[].skinID: very large: 3655218992
  - arg0[].paramsID: very large: 4251336912
- **Examples (3):**

  **Example 1:**
  ```
  arg0: ListContainer([Container(paramsID=4170597200, ownerID=1041047, salvoID=0, skinID...
  ```

  **Example 2:**
  ```
  arg0: ListContainer([Container(paramsID=4170597200, ownerID=1041047, salvoID=0, skinID...
  ```

  **Example 3:**
  ```
  arg0: ListContainer([Container(paramsID=4170597200, ownerID=1041047, salvoID=0, skinID...
  ```

### `Vehicle.kill`

- **Calls:** 20 | **Decoded:** 20 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
  - `arg2`: `int`
  - `arg3`: `float`
  - `arg4`: `int`
  - `arg5`: `Container`
  - `arg6`: `Container`
  - `arg7`: `Container`
  - `arg8`: `int`
- **Suspicious values:**
  - arg2: very large: 4229939408
  - arg2: very large: 4159685424
  - arg2: very large: 3340747536
  - arg2: very large: 4189045712
  - arg2: very large: 4279222608
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 0
  arg1: 6
  arg2: 0
  arg3: 70.0
  arg4: 0
  arg5: Container(x=0.10840880870819092, y=23.693395614624023)
  arg6: Container(x=0.0, y=0.0, z=0.0)
  arg7: Container(x=-1.6569024324417114, y=3.2949001600030003e-12, z=-0.9473815560340881...
  arg8: 1041033
  ```

  **Example 2:**
  ```
  arg0: 0
  arg1: 18
  arg2: 4229939408
  arg3: 80.0
  arg4: 2
  arg5: Container(x=-0.06702892482280731, y=29.878725051879883)
  arg6: Container(x=0.21828842163085938, y=0.4035959243774414, z=-0.35706329345703125)
  arg7: Container(x=-1.4625465869903564, y=0.15255537629127502, z=1.519732117652893)
  arg8: 1041045
  ```

  **Example 3:**
  ```
  arg0: 0
  arg1: 17
  arg2: 4159685424
  arg3: 70.0
  arg4: 0
  arg5: Container(x=-0.02864513359963894, y=-170.0)
  arg6: Container(x=1.19903564453125, y=0.13744354248046875, z=-2.8746337890625)
  arg7: Container(x=-13.082656860351562, y=-9.506932130420864e-09, z=29.10858917236328)
  arg8: 1041039
  ```

### `Vehicle.receiveDamagesOnShip`

- **Calls:** 1,161 | **Decoded:** 1,161 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `ListContainer`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: ListContainer([Container(vehicleID=1041043, damage=2112.0)])
  ```

  **Example 2:**
  ```
  arg0: ListContainer([Container(vehicleID=1041051, damage=2013.0)])
  ```

  **Example 3:**
  ```
  arg0: ListContainer([Container(vehicleID=1041039, damage=12404.0)])
  ```

### `Vehicle.receiveHitLocationStateChange`

- **Calls:** 2,922 | **Decoded:** 2,922 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
- **Suspicious values:**
  - arg1: very large: 20482932
  - arg1: very large: 49154852
  - arg1: very large: 32771034
  - arg1: very large: 32648123
  - arg1: very large: 32418716
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 4000
  arg1: 904
  ```

  **Example 2:**
  ```
  arg0: 13000
  arg1: 1014
  ```

  **Example 3:**
  ```
  arg0: 4000
  arg1: 785
  ```

### `Vehicle.receiveHitLocationsInitialState`

- **Calls:** 100 | **Decoded:** 100 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `ListContainer`
  - `arg1`: `ListContainer`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: ListContainer([])
  arg1: ListContainer([])
  ```

  **Example 2:**
  ```
  arg0: [2, 3] ... (6 items)
  arg1: [834, 983] ... (6 items)
  ```

  **Example 3:**
  ```
  arg0: ListContainer([4, 88])
  arg1: ListContainer([887, 1015])
  ```

### `Vehicle.resetResettableWaveEnemyHits`

- **Calls:** 4 | **Decoded:** 4 (100.0%) | **Failed:** 0
- **Examples (1):**

  **Example 1:**
  ```
  ```

### `Vehicle.setUniqueSkills`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `bytes`
- **Examples (1):**

  **Example 1:**
  ```
  arg0: b'\x80\x02}q\x01U\x08triggersq\x02]q\x03(}q\x04(U\tachEarnedq\x05K\x00U\ntrigger...
  ```

### `Vehicle.shootTorpedo`

- **Calls:** 46 | **Decoded:** 46 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `Container`
  - `arg2`: `int`
  - `arg3`: `int`
  - `arg4`: `int`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 0
  arg1: Container(x=-0.5368195176124573, y=0.0, z=0.8436970710754395)
  arg2: 0
  arg3: 0
  arg4: 0
  ```

  **Example 2:**
  ```
  arg0: 2
  arg1: Container(x=-0.5205413103103638, y=0.0, z=0.8538364768028259)
  arg2: 1
  arg3: 0
  arg4: 0
  ```

  **Example 3:**
  ```
  arg0: 1
  arg1: Container(x=-0.2719796597957611, y=0.0, z=0.9623029828071594)
  arg2: 2
  arg3: 0
  arg4: 0
  ```

### `Vehicle.syncTorpedoState`

- **Calls:** 100 | **Decoded:** 100 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
- **Examples (1):**

  **Example 1:**
  ```
  arg0: 0
  ```

### `Vehicle.syncTorpedoTube`

- **Calls:** 70 | **Decoded:** 70 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `float`
  - `arg2`: `float`
  - `arg3`: `int`
  - `arg4`: `float`
  - `arg5`: `int`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 0
  arg1: 0.0
  arg2: 0.0
  arg3: 1
  arg4: 1.0
  arg5: 0
  ```

  **Example 2:**
  ```
  arg0: 1
  arg1: 0.0
  arg2: 0.0
  arg3: 1
  arg4: 1.0
  arg5: 0
  ```

  **Example 3:**
  ```
  arg0: 2
  arg1: 0.0
  arg2: 0.0
  arg3: 1
  arg4: 1.0
  arg5: 0
  ```

## 3. Game State

### `Avatar.activateAirSupport`

- **Calls:** 8 | **Decoded:** 8 (100.0%) | **Failed:** 0
- **Fields:**
  - `index`: `int`
  - `squadronID`: `int`
  - `position`: `Container`
  - `aimLength`: `float`
  - `airSupportShotID`: `int`
- **Suspicious values:**
  - squadronID: very large: 210454438513
  - squadronID: very large: 760210252401
  - squadronID: very large: 1309966066289
  - squadronID: very large: 1859721880177
  - squadronID: very large: 2409477694065
- **Examples (3):**

  **Example 1:**
  ```
  index: 0
  squadronID: 210454438513
  position: Container(x=233.15403747558594, y=0.0, z=228.83201599121094)
  aimLength: 22.595491409301758
  airSupportShotID: 85
  ```

  **Example 2:**
  ```
  index: 1
  squadronID: 760210252401
  position: Container(x=-214.50047302246094, y=0.0, z=-75.81396484375)
  aimLength: 22.595537185668945
  airSupportShotID: 169
  ```

  **Example 3:**
  ```
  index: 0
  squadronID: 1309966066289
  position: Container(x=-186.3297119140625, y=0.0, z=-15.857421875)
  aimLength: 22.59552001953125
  airSupportShotID: 276
  ```

### `Avatar.beginOwnerlessTracers`

- **Calls:** 49 | **Decoded:** 49 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
  - `arg2`: `int`
- **Suspicious values:**
  - arg2: very large: 210454438513
  - arg2: very large: 760210252401
  - arg2: very large: 1309966066289
  - arg2: very large: 1859721880177
  - arg2: very large: 2409477694065
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 1041031
  arg1: 0
  arg2: 210454438513
  ```

  **Example 2:**
  ```
  arg0: 1041031
  arg1: 2
  arg2: 210454438513
  ```

  **Example 3:**
  ```
  arg0: 1041031
  arg1: 3
  arg2: 210454438513
  ```

### `Avatar.changePreBattleGrants`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `grants`: `int`
- **Examples (1):**

  **Example 1:**
  ```
  grants: 208886
  ```

### `Avatar.deactivateAirSupport`

- **Calls:** 8 | **Decoded:** 8 (100.0%) | **Failed:** 0
- **Fields:**
  - `index`: `int`
  - `squadronID`: `int`
- **Suspicious values:**
  - squadronID: very large: 210454438513
  - squadronID: very large: 760210252401
  - squadronID: very large: 1309966066289
  - squadronID: very large: 1859721880177
  - squadronID: very large: 2409477694065
- **Examples (3):**

  **Example 1:**
  ```
  index: 0
  squadronID: 210454438513
  ```

  **Example 2:**
  ```
  index: 1
  squadronID: 760210252401
  ```

  **Example 3:**
  ```
  index: 0
  squadronID: 1309966066289
  ```

### `Avatar.endOwnerlessTracers`

- **Calls:** 49 | **Decoded:** 49 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
  - `arg2`: `int`
- **Suspicious values:**
  - arg2: very large: 210454438513
  - arg2: very large: 760210252401
  - arg2: very large: 1309966066289
  - arg2: very large: 1859721880177
  - arg2: very large: 2409477694065
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 1041031
  arg1: 2
  arg2: 210454438513
  ```

  **Example 2:**
  ```
  arg0: 1041031
  arg1: 3
  arg2: 210454438513
  ```

  **Example 3:**
  ```
  arg0: 1041031
  arg1: 0
  arg2: 210454438513
  ```

### `Avatar.onArenaStateReceived`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `arenaUniqueId`: `int`
  - `teamBuildTypeId`: `int`
  - `preBattlesInfo`: `bytes`
  - `playersStates`: `bytes`
  - `botsStates`: `bytes`
  - `observersState`: `bytes`
  - `buildingsInfo`: `bytes`
- **Suspicious values:**
  - arenaUniqueId: very large: 4471079909201971
- **Examples (1):**

  **Example 1:**
  ```
  arenaUniqueId: 4471079909201971
  teamBuildTypeId: 0
  preBattlesInfo: b'\x80\x02}q\x01(K\x00]q\x02(}q\x03(U\x04infoq\x04}U\x02idq\x05J\x1f\x18\xd0\x1d...
  playersStates: b'\x80\x02]q\x01(]q\x02(K\x00J\x8b\xe8\xf3\x1d\x86q\x03K\x01\x88\x86q\x04K\x02Jn...
  botsStates: b'\x80\x02].'
  observersState: b'\x80\x02].'
  buildingsInfo: b'\x80\x02].'
  ```

### `Avatar.onBattleEnd`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Examples (1):**

  **Example 1:**
  ```
  ```

### `Avatar.onConnected`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `artilleryAmmoId`: `int`
  - `torpdoAmmoId`: `int`
  - `airSupportAmmoId`: `int`
  - `torpedoSelectedAngle`: `int`
  - `weaponLocks`: `ListContainer`
- **Suspicious values:**
  - artilleryAmmoId: very large: 3339698960
  - airSupportAmmoId: very large: 4279140112
- **Examples (1):**

  **Example 1:**
  ```
  artilleryAmmoId: 3339698960
  torpdoAmmoId: 0
  airSupportAmmoId: 4279140112
  torpedoSelectedAngle: 0
  weaponLocks: ListContainer([])
  ```

### `Avatar.onEnterPreBattle`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `packedPreBattleData`: `bytes`
  - `grants`: `int`
  - `isRecreated`: `int`
- **Examples (1):**

  **Example 1:**
  ```
  packedPreBattleData: b'x\x01m\x91?o\x131\x18\xc6\x9d?$\xcdQBB\x99\x90RE\x99\x8e\x05\xf9\xdf\xf9|s\x93...
  grants: 320
  isRecreated: 0
  ```

### `Avatar.onGameRoomStateChanged`

- **Calls:** 88 | **Decoded:** 88 (100.0%) | **Failed:** 0
- **Fields:**
  - `playersData`: `bytes`
  - `botsData`: `bytes`
  - `observersData`: `bytes`
- **Examples (3):**

  **Example 1:**
  ```
  playersData: b'\x80\x02]q\x01]q\x02(K\x0bJ`b\x178\x86q\x03K\x11\x88\x86q\x04ea.'
  botsData: b'\x80\x02].'
  observersData: b'\x80\x02].'
  ```

  **Example 2:**
  ```
  playersData: b'\x80\x02]q\x01]q\x02(K\x0bJ)\xf0\x100\x86q\x03K\x11\x88\x86q\x04ea.'
  botsData: b'\x80\x02].'
  observersData: b'\x80\x02].'
  ```

  **Example 3:**
  ```
  playersData: b'\x80\x02]q\x01]q\x02(K\x0bJQ\x0c\x0e0\x86q\x03K\x11\x88\x86q\x04ea.'
  botsData: b'\x80\x02].'
  observersData: b'\x80\x02].'
  ```

### `Avatar.onOwnerChanged`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `ownerId`: `int`
  - `isOwner`: `int`
- **Suspicious values:**
  - ownerId: very large: 806471823
- **Examples (1):**

  **Example 1:**
  ```
  ownerId: 806471823
  isOwner: 1
  ```

### `Avatar.onShutdownTime`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
  - `arg2`: `int`
- **Examples (1):**

  **Example 1:**
  ```
  arg0: 0
  arg1: 0
  arg2: 0
  ```

### `Avatar.onWorldStateReceived`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Examples (1):**

  **Example 1:**
  ```
  ```

### `Avatar.receiveAvatarInfo`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `bytes`
- **Examples (1):**

  **Example 1:**
  ```
  arg0: b'\x80\x02}q\x01(U\x0fevaluationsLeftq\x02}q\x03(K\x00K\x0fK\x01K\x0euU\x14strat...
  ```

### `Avatar.receiveExplosions`

- **Calls:** 64 | **Decoded:** 64 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `ListContainer`
- **Suspicious values:**
  - arg0[].paramsID: very large: 4265591248
  - arg0[].paramsID: very large: 4269785392
  - arg0[].paramsID: very large: 4279222608
  - arg0[].paramsID: very large: 4278174032
  - arg0[].paramsID: very large: 4277126096
- **Examples (3):**

  **Example 1:**
  ```
  arg0: ListContainer([Container(pos=Container(x=-185.93116760253906, y=0.69571506977081...
  ```

  **Example 2:**
  ```
  arg0: ListContainer([Container(pos=Container(x=-190.1324005126953, y=0.170182123780250...
  ```

  **Example 3:**
  ```
  arg0: ListContainer([Container(pos=Container(x=73.8719253540039, y=0.2497718185186386,...
  ```

### `Avatar.receivePlaneProjectilePack`

- **Calls:** 156 | **Decoded:** 156 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `ListContainer`
- **Suspicious values:**
  - arg0[].bombParamsId: very large: 4182655984
  - arg0[].squadronId: very large: 210454438555
  - arg0[].bombParamsId: very large: 4268704528
  - arg0[].squadronId: very large: 210454438513
  - arg0[].squadronId: very large: 760210252401
- **Examples (3):**

  **Example 1:**
  ```
  arg0: ListContainer([Container(bombParamsId=4182655984, squadronId=210454438555, squad...
  ```

  **Example 2:**
  ```
  arg0: ListContainer([Container(bombParamsId=4182655984, squadronId=210454438555, squad...
  ```

  **Example 3:**
  ```
  arg0: ListContainer([Container(bombParamsId=4268704528, squadronId=210454438513, squad...
  ```

### `Avatar.receivePlayerData`

- **Calls:** 2 | **Decoded:** 2 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `bytes`
  - `arg1`: `int`
- **Examples (2):**

  **Example 1:**
  ```
  arg0: b'\x80\x02(J\xf0\xbc\x0e8J\x92\x1e\x93"U\x10Milch_vor_Muesliq\x01NK\x00K\x01\x89...
  arg1: 0
  ```

  **Example 2:**
  ```
  arg0: b'\x80\x02(J\xf0\xbc\x0e8J\x92\x1e\x93"U\x10Milch_vor_Muesliq\x01NJ\xfe\xff\xff\...
  arg1: 0
  ```

### `Avatar.receiveVehicleDeath`

- **Calls:** 20 | **Decoded:** 20 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
  - `arg2`: `int`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 1041021
  arg1: 1041033
  arg2: 6
  ```

  **Example 2:**
  ```
  arg0: 1041019
  arg1: 1041045
  arg2: 18
  ```

  **Example 3:**
  ```
  arg0: 1041051
  arg1: 1041039
  arg2: 17
  ```

### `Avatar.receive_CommonCMD`

- **Calls:** 35 | **Decoded:** 35 (100.0%) | **Failed:** 0
- **Fields:**
  - `playerId`: `int`
  - `command`: `bytes`
- **Suspicious values:**
  - playerId: very large: 806471823
  - playerId: very large: 806449305
  - playerId: very large: 806416425
  - playerId: very large: 940523857
  - playerId: very large: 940489968
- **Examples (3):**

  **Example 1:**
  ```
  playerId: 806471823
  command: b'\x12\x00\x00\xa7\xe0\xc1C/\x92d\xc3'
  ```

  **Example 2:**
  ```
  playerId: 806471823
  command: b'\x12\x00\x00\xb7C#C\xcc>TC'
  ```

  **Example 3:**
  ```
  playerId: 806471823
  command: b'\x12\x00\x00\xfb\xd0\xf0C9\x1a\x1bC'
  ```

### `Avatar.receive_addMinimapSquadron`

- **Calls:** 11 | **Decoded:** 11 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
  - `arg2`: `int`
  - `arg3`: `Container`
  - `arg4`: `int`
- **Suspicious values:**
  - arg0: very large: 141734961793
  - arg2: very large: 3343318832
  - arg0: very large: 210454438555
  - arg2: very large: 3346955600
  - arg0: very large: 210454438513
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 141734961793
  arg1: 1
  arg2: 3343318832
  arg3: Container(x=-602.8699951171875, y=-326.7699890136719)
  arg4: 0
  ```

  **Example 2:**
  ```
  arg0: 210454438555
  arg1: 1
  arg2: 3346955600
  arg3: Container(x=-724.5999755859375, y=-24.520000457763672)
  arg4: 0
  ```

  **Example 3:**
  ```
  arg0: 210454438513
  arg1: 1
  arg2: 4279140112
  arg3: Container(x=175.36000061035156, y=84.37000274658203)
  arg4: 0
  ```

### `Avatar.receive_addSquadron`

- **Calls:** 11 | **Decoded:** 11 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
  - `arg2`: `Container`
  - `arg3`: `int`
  - `arg4`: `int`
  - `arg5`: `float`
  - `arg6`: `int`
- **Suspicious values:**
  - arg0: very large: 3343318832
  - arg0: very large: 3346955600
  - arg0: very large: 4279140112
  - arg6: very large: 9817068105
  - arg0: very large: 4287037136
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 3343318832
  arg1: 1
  arg2: Container(planeID=141734961793, skinID=4178523952, isActive=1, numPlanes=1, posi...
  arg3: 0
  arg4: 2204
  arg5: 1.0
  arg6: 1
  ```

  **Example 2:**
  ```
  arg0: 3346955600
  arg1: 1
  arg2: Container(planeID=210454438555, skinID=4108971952, isActive=1, numPlanes=1, posi...
  arg3: 0
  arg4: 2050
  arg5: 1.0
  arg6: 1
  ```

  **Example 3:**
  ```
  arg0: 4279140112
  arg1: 12
  arg2: Container(planeID=210454438513, skinID=4074368944, isActive=1, numPlanes=12, pos...
  arg3: 0
  arg4: 2255
  arg5: 1.0
  arg6: 9817068105
  ```

### `Avatar.receive_changeState`

- **Calls:** 31 | **Decoded:** 31 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
  - `arg2`: `int`
- **Suspicious values:**
  - arg0: very large: 141734961793
  - arg0: very large: 210454438555
  - arg0: very large: 210454438513
  - arg0: very large: 760210252401
  - arg0: very large: 1309966066289
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 141734961793
  arg1: 0
  arg2: 1
  ```

  **Example 2:**
  ```
  arg0: 141734961793
  arg1: 1
  arg2: 3
  ```

  **Example 3:**
  ```
  arg0: 210454438555
  arg1: 0
  arg2: 3
  ```

### `Avatar.receive_deactivateSquadron`

- **Calls:** 10 | **Decoded:** 10 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
- **Suspicious values:**
  - arg0: very large: 210454438555
  - arg0: very large: 141734961793
  - arg0: very large: 210454438513
  - arg0: very large: 760210252401
  - arg0: very large: 1309966066289
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 210454438555
  arg1: 1
  ```

  **Example 2:**
  ```
  arg0: 141734961793
  arg1: 1
  ```

  **Example 3:**
  ```
  arg0: 210454438513
  arg1: 9
  ```

### `Avatar.receive_planeDeath`

- **Calls:** 26 | **Decoded:** 26 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `ListContainer`
  - `arg2`: `int`
  - `arg3`: `int`
- **Suspicious values:**
  - arg0: very large: 210454438513
  - arg0: very large: 760210252401
  - arg0: very large: 1309966066289
  - arg0: very large: 1859721880177
  - arg0: very large: 2409477694065
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 210454438513
  arg1: ListContainer([11])
  arg2: 1
  arg3: 1041031
  ```

  **Example 2:**
  ```
  arg0: 210454438513
  arg1: ListContainer([10])
  arg2: 1
  arg3: 1041031
  ```

  **Example 3:**
  ```
  arg0: 210454438513
  arg1: ListContainer([9])
  arg2: 1
  arg3: 1041031
  ```

### `Avatar.receive_refresh`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `bytes`
- **Examples (1):**

  **Example 1:**
  ```
  arg0: b'\x80\x02}G\x00\x00\x00\x00\x00\x00\x00\x00\x86]q\x01\x86q\x02.'
  ```

### `Avatar.receive_removeMinimapSquadron`

- **Calls:** 11 | **Decoded:** 11 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
- **Suspicious values:**
  - arg0: very large: 210454438555
  - arg0: very large: 141734961793
  - arg0: very large: 210454438513
  - arg0: very large: 760210252401
  - arg0: very large: 141734961775
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 210454438555
  ```

  **Example 2:**
  ```
  arg0: 141734961793
  ```

  **Example 3:**
  ```
  arg0: 210454438513
  ```

### `Avatar.receive_removeSquadron`

- **Calls:** 11 | **Decoded:** 11 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
- **Suspicious values:**
  - arg0: very large: 210454438555
  - arg0: very large: 141734961793
  - arg0: very large: 210454438513
  - arg0: very large: 760210252401
  - arg0: very large: 141734961775
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 210454438555
  ```

  **Example 2:**
  ```
  arg0: 141734961793
  ```

  **Example 3:**
  ```
  arg0: 210454438513
  ```

### `Avatar.receive_resetWaypoints`

- **Calls:** 122 | **Decoded:** 122 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `ListContainer`
- **Suspicious values:**
  - arg0: very large: 141734961793
  - arg0: very large: 210454438555
  - arg0: very large: 210454438513
  - arg0: very large: 760210252401
  - arg0: very large: 1309966066289
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 141734961793
  arg1: ListContainer([Container(position=Container(x=-603.08740234375, y=4.427887916564...
  ```

  **Example 2:**
  ```
  arg0: 141734961793
  arg1: ListContainer([Container(position=Container(x=-603.08740234375, y=5.033757686614...
  ```

  **Example 3:**
  ```
  arg0: 141734961793
  arg1: ListContainer([Container(position=Container(x=-603.08740234375, y=5.693192481994...
  ```

### `Avatar.receive_squadronHealth`

- **Calls:** 392 | **Decoded:** 392 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `float`
- **Suspicious values:**
  - arg0: very large: 141734961793
  - arg0: very large: 210454438555
  - arg0: very large: 210454438513
  - arg0: very large: 760210252401
  - arg0: very large: 1309966066289
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 141734961793
  arg1: 1.0
  ```

  **Example 2:**
  ```
  arg0: 210454438555
  arg1: 1.0
  ```

  **Example 3:**
  ```
  arg0: 210454438555
  arg1: 0.9912195205688477
  ```

### `Avatar.receive_squadronPlanesHealth`

- **Calls:** 94 | **Decoded:** 94 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
- **Suspicious values:**
  - arg0: very large: 141734961793
  - arg0: very large: 210454438555
  - arg0: very large: 210454438513
  - arg1: very large: 9817068105
  - arg1: very large: 18407002697
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 141734961793
  arg1: 1
  ```

  **Example 2:**
  ```
  arg0: 210454438555
  arg1: 1
  ```

  **Example 3:**
  ```
  arg0: 210454438555
  arg1: 2
  ```

### `Avatar.receive_squadronVisibilityChanged`

- **Calls:** 16 | **Decoded:** 16 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
- **Suspicious values:**
  - arg0: very large: 210454438513
  - arg0: very large: 760210252401
  - arg0: very large: 1309966066289
  - arg0: very large: 1859721880177
  - arg0: very large: 2409477694065
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 210454438513
  arg1: 1
  ```

  **Example 2:**
  ```
  arg0: 210454438513
  arg1: 0
  ```

  **Example 3:**
  ```
  arg0: 760210252401
  arg1: 1
  ```

### `Avatar.receive_stopManeuvering`

- **Calls:** 10 | **Decoded:** 10 (100.0%) | **Failed:** 0
- **Fields:**
  - `squadronId`: `int`
- **Suspicious values:**
  - squadronId: very large: 210454438555
  - squadronId: very large: 141734961793
  - squadronId: very large: 210454438513
  - squadronId: very large: 760210252401
  - squadronId: very large: 1309966066289
- **Examples (3):**

  **Example 1:**
  ```
  squadronId: 210454438555
  ```

  **Example 2:**
  ```
  squadronId: 141734961793
  ```

  **Example 3:**
  ```
  squadronId: 210454438513
  ```

### `Avatar.receive_updateMinimapSquadron`

- **Calls:** 170 | **Decoded:** 170 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `Container`
- **Suspicious values:**
  - arg0: very large: 141734961793
  - arg0: very large: 210454438555
  - arg0: very large: 210454438513
  - arg0: very large: 760210252401
  - arg0: very large: 141734961775
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 141734961793
  arg1: Container(x=-599.0900268554688, y=-317.1199951171875)
  ```

  **Example 2:**
  ```
  arg0: 141734961793
  arg1: Container(x=-602.6900024414062, y=-305.760009765625)
  ```

  **Example 3:**
  ```
  arg0: 141734961793
  arg1: Container(x=-602.3699951171875, y=-291.07000732421875)
  ```

### `Avatar.receive_updateSquadron`

- **Calls:** 308 | **Decoded:** 308 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `float`
  - `arg2`: `ListContainer`
- **Suspicious values:**
  - arg0: very large: 141734961793
  - arg0: very large: 210454438555
  - arg0: very large: 210454438513
  - arg0: very large: 760210252401
  - arg0: very large: 141734961775
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 141734961793
  arg1: 0.1428571492433548
  arg2: ListContainer([Container(position=Container(x=-603.08740234375, y=0.733999967575...
  ```

  **Example 2:**
  ```
  arg0: 141734961793
  arg1: 0.13285714387893677
  arg2: ListContainer([Container(position=Container(x=-603.088623046875, y=16.7283439636...
  ```

  **Example 3:**
  ```
  arg0: 141734961793
  arg1: 0.27571427822113037
  arg2: [Container(position=Container(x=-603.088623046875, y=16.728343963623047, z=-296....
  ```

### `Avatar.startDissapearing`

- **Calls:** 97 | **Decoded:** 97 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 1041039
  ```

  **Example 2:**
  ```
  arg0: 1041041
  ```

  **Example 3:**
  ```
  arg0: 1041007
  ```

### `Avatar.updateCoolDown`

- **Calls:** 11 | **Decoded:** 11 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `bytes`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: b'\x80\x02]q\x01J`b\x178J4\x18\xc0i\x86q\x02a.'
  ```

  **Example 2:**
  ```
  arg0: b'\x80\x02]q\x01J|D\x130J4\x18\xc0i\x86q\x02a.'
  ```

  **Example 3:**
  ```
  arg0: b'\x80\x02]q\x01J)\xf0\x100J4\x18\xc0i\x86q\x02a.'
  ```

### `Avatar.updateMinimapVisionInfo`

- **Calls:** 1,938 | **Decoded:** 1,938 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `ListContainer`
  - `arg1`: `ListContainer`
- **Suspicious values:**
  - arg0[].packedData: very large: 538532649
  - arg0[].packedData: very large: 538533083
  - arg0[].packedData: very large: 538532832
  - arg0[].packedData: very large: 538590209
  - arg0[].packedData: very large: 538590427
- **Examples (3):**

  **Example 1:**
  ```
  arg0: [Container(vehicleID=1041025, packedData=538532649), Container(vehicleID=1041035...
  arg1: ListContainer([])
  ```

  **Example 2:**
  ```
  arg0: ListContainer([Container(vehicleID=1041021, packedData=534371096)])
  arg1: ListContainer([])
  ```

  **Example 3:**
  ```
  arg0: ListContainer([Container(vehicleID=1041047, packedData=534398171)])
  arg1: ListContainer([])
  ```

### `Avatar.updateOwnerlessAuraState`

- **Calls:** 77 | **Decoded:** 77 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
  - `arg2`: `int`
  - `arg3`: `int`
- **Suspicious values:**
  - arg2: very large: 210454438513
  - arg2: very large: 760210252401
  - arg2: very large: 1309966066289
  - arg2: very large: 1859721880177
  - arg2: very large: 2409477694065
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 1041031
  arg1: 0
  arg2: 210454438513
  arg3: 3
  ```

  **Example 2:**
  ```
  arg0: 1041031
  arg1: 2
  arg2: 210454438513
  arg3: 3
  ```

  **Example 3:**
  ```
  arg0: 1041031
  arg1: 3
  arg2: 210454438513
  arg3: 3
  ```

### `Avatar.updatePreBattlesInfo`

- **Calls:** 22 | **Decoded:** 22 (100.0%) | **Failed:** 0
- **Fields:**
  - `packedData`: `bytes`
- **Examples (3):**

  **Example 1:**
  ```
  packedData: b'\x80\x02(J\xcb:\x1a8K\x00K\x00J\x13\x8d\x128I1774196778929\n\x89\x88t.'
  ```

  **Example 2:**
  ```
  packedData: b'\x80\x02(J\xa4S\x1a8K\x02K\x00J\xe3b\x170I1774196778929\n\x89\x88t.'
  ```

  **Example 3:**
  ```
  packedData: b'\x80\x02(J\xe6\xad\x1a8K\x01K\x00J\x8f\xc8\x110I1774196778930\n\x89\x89t.'
  ```

### `Vehicle.makeShipCracksActive`

- **Calls:** 18 | **Decoded:** 18 (100.0%) | **Failed:** 0
- **Examples (1):**

  **Example 1:**
  ```
  ```

### `Vehicle.onConsumableInterrupted`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
- **Examples (1):**

  **Example 1:**
  ```
  arg0: 10
  ```

### `Vehicle.onConsumableUsed`

- **Calls:** 102 | **Decoded:** 102 (100.0%) | **Failed:** 0
- **Fields:**
  - `consumableUsageParams`: `bytes`
  - `workTimeLeft`: `float`
- **Examples (3):**

  **Example 1:**
  ```
  consumableUsageParams: b'\x01\n'
  workTimeLeft: 132.0
  ```

  **Example 2:**
  ```
  consumableUsageParams: b'\x01\x01'
  workTimeLeft: 100.0
  ```

  **Example 3:**
  ```
  consumableUsageParams: b'\x01\n'
  workTimeLeft: 121.0
  ```

### `Vehicle.onCrashCrewDisable`

- **Calls:** 4 | **Decoded:** 4 (100.0%) | **Failed:** 0
- **Examples (1):**

  **Example 1:**
  ```
  ```

### `Vehicle.onCrashCrewEnable`

- **Calls:** 4 | **Decoded:** 4 (100.0%) | **Failed:** 0
- **Examples (1):**

  **Example 1:**
  ```
  ```

### `Vehicle.onPrioritySectorSet`

- **Calls:** 7 | **Decoded:** 7 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `float`
- **Examples (2):**

  **Example 1:**
  ```
  arg0: 0
  arg1: 0.0
  ```

  **Example 2:**
  ```
  arg0: 1
  arg1: 0.0
  ```

### `Vehicle.onWeaponStateSwitched`

- **Calls:** 2 | **Decoded:** 2 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
- **Examples (2):**

  **Example 1:**
  ```
  arg0: 0
  arg1: 1
  ```

  **Example 2:**
  ```
  arg0: 0
  arg1: 0
  ```

### `Vehicle.receiveGunSyncRotations`

- **Calls:** 18 | **Decoded:** 18 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 0
  arg1: 2308
  ```

  **Example 2:**
  ```
  arg0: 2
  arg1: 1284
  ```

  **Example 3:**
  ```
  arg0: 0
  arg1: 5380
  ```

### `Vehicle.setAirDefenseState`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `bytes`
- **Examples (1):**

  **Example 1:**
  ```
  arg0: b'\x80\x02(J\xff\xff\xff\xffJ\xff\xff\xff\xffK\x00NG\x00\x00\x00\x00\x00\x00\x00...
  ```

### `Vehicle.setAmmoForWeapon`

- **Calls:** 43 | **Decoded:** 43 (100.0%) | **Failed:** 0
- **Fields:**
  - `weaponType`: `int`
  - `ammoParamsId`: `int`
  - `isReload`: `int`
- **Suspicious values:**
  - ammoParamsId: very large: 4255105360
  - ammoParamsId: very large: 4193239504
  - ammoParamsId: very large: 4145005392
  - ammoParamsId: very large: 4173316912
  - ammoParamsId: very large: 4282369008
- **Examples (3):**

  **Example 1:**
  ```
  weaponType: 0
  ammoParamsId: 4255105360
  isReload: 1
  ```

  **Example 2:**
  ```
  weaponType: 0
  ammoParamsId: 4193239504
  isReload: 1
  ```

  **Example 3:**
  ```
  weaponType: 0
  ammoParamsId: 4145005392
  isReload: 1
  ```

### `Vehicle.setConsumables`

- **Calls:** 100 | **Decoded:** 100 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `bytes`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: b'\x80\x02}q\x01(U\x11specialConsumableq\x02NU\x0fconsumablesDictq\x03]q\x04(K\x...
  ```

  **Example 2:**
  ```
  arg0: b'\x80\x02}q\x01(U\x11specialConsumableq\x02NU\x0fconsumablesDictq\x03]q\x04(K\x...
  ```

  **Example 3:**
  ```
  arg0: b'\x80\x02}q\x01(U\x11specialConsumableq\x02NU\x0fconsumablesDictq\x03]q\x04(K\x...
  ```

### `Vehicle.setReloadingStateForWeapon`

- **Calls:** 5 | **Decoded:** 5 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `bytes`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 5
  arg1: b'\x80\x02K\x02G\x00\x00\x00\x00\x00\x00\x00\x00\x86.'
  ```

  **Example 2:**
  ```
  arg0: 0
  arg1: b'\x80\x02}q\x01(K\x00(G?\xf0\x00\x00\x00\x00\x00\x00]q\x02(cGameParams\nGPData\...
  ```

  **Example 3:**
  ```
  arg0: 2
  arg1: b'\x80\x02}q\x01(U\x08reloaderq\x02NU\x04gunsq\x03}u.'
  ```

### `Vehicle.shootATBAGuns`

- **Calls:** 888 | **Decoded:** 888 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 1
  ```

  **Example 2:**
  ```
  arg0: 260
  ```

  **Example 3:**
  ```
  arg0: 8192
  ```

### `Vehicle.shootOnClient`

- **Calls:** 1,173 | **Decoded:** 1,173 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 0
  arg1: 1
  ```

  **Example 2:**
  ```
  arg0: 0
  arg1: 2
  ```

  **Example 3:**
  ```
  arg0: 0
  arg1: 4
  ```

### `Vehicle.syncGun`

- **Calls:** 450 | **Decoded:** 450 (100.0%) | **Failed:** 0
- **Fields:**
  - `weaponType`: `int`
  - `gunId`: `int`
  - `yaw`: `float`
  - `pitch`: `float`
  - `alive`: `int`
  - `reloadPerc`: `float`
  - `loadedAmmo`: `ListContainer`
- **Examples (3):**

  **Example 1:**
  ```
  weaponType: 0
  gunId: 0
  yaw: 0.0
  pitch: 0.0
  alive: 1
  reloadPerc: 0.0
  loadedAmmo: ListContainer([])
  ```

  **Example 2:**
  ```
  weaponType: 0
  gunId: 1
  yaw: 0.0
  pitch: 0.0
  alive: 1
  reloadPerc: 0.0
  loadedAmmo: ListContainer([])
  ```

  **Example 3:**
  ```
  weaponType: 0
  gunId: 2
  yaw: 0.0
  pitch: 0.0
  alive: 1
  reloadPerc: 0.0
  loadedAmmo: ListContainer([])
  ```

### `Vehicle.uniqueTriggerActivated`

- **Calls:** 3 | **Decoded:** 3 (100.0%) | **Failed:** 0
- **Examples (1):**

  **Example 1:**
  ```
  ```

## 4. Meta / Stats / Chat

### `Avatar.onAchievementEarned`

- **Calls:** 4 | **Decoded:** 4 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
- **Suspicious values:**
  - arg0: very large: 806569048
  - arg1: very large: 4277330864
  - arg0: very large: 806839011
  - arg1: very large: 4273136560
  - arg0: very large: 806471823
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 806569048
  arg1: 4277330864
  ```

  **Example 2:**
  ```
  arg0: 806839011
  arg1: 4273136560
  ```

  **Example 3:**
  ```
  arg0: 806471823
  arg1: 3911377840
  ```

### `Avatar.onChatMessage`

- **Calls:** 37 | **Decoded:** 35 (94.6%) | **Failed:** 2
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `str`
  - `arg2`: `str`
  - `arg3`: `str`
- **Suspicious values:**
  - arg0: very large: 940739859
  - arg0: very large: 940489968
  - arg0: very large: 806406716
  - arg0: very large: 806471823
  - arg0: very large: 806720509
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 940739859
  arg1: 'battle_common'
  arg2: 'o7 Dutch'
  arg3: ''
  ```

  **Example 2:**
  ```
  arg0: 940739859
  arg1: 'battle_common'
  arg2: 'Ruslan only plays moskva 24/7 fellas.'
  arg3: ''
  ```

  **Example 3:**
  ```
  arg0: 940739859
  arg1: 'battle_common'
  arg2: 'watch out we got a superstar'
  arg3: ''
  ```

### `Avatar.receiveChatHistory`

- **Calls:** 1 | **Decoded:** 1 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `bytes`
- **Examples (1):**

  **Example 1:**
  ```
  arg0: b'x\x9ck`\x8a-d\xd4\x03\x00\x06\x07\x01\x80'
  ```

### `Avatar.receiveShellInfo`

- **Calls:** 279 | **Decoded:** 279 (100.0%) | **Failed:** 0
- **Fields:**
  - `arg0`: `int`
  - `arg1`: `int`
  - `arg2`: `int`
  - `arg3`: `int`
  - `arg4`: `int`
  - `arg5`: `int`
  - `arg6`: `int`
  - `arg7`: `int`
  - `arg8`: `int`
  - `arg9`: `int`
  - `arg10`: `ListContainer`
- **Suspicious values:**
  - arg0: very large: 3340747536
  - arg0: very large: 3339698960
  - arg0: very large: 4260348368
  - arg0: very large: 4278174032
  - arg0: very large: 4292854768
- **Examples (3):**

  **Example 1:**
  ```
  arg0: 3340747536
  arg1: 34
  arg2: 89
  arg3: 1041011
  arg4: 575
  arg5: 309
  arg6: 8684682
  arg7: 44
  arg8: 40
  arg9: 2
  arg10: ListContainer([])
  ```

  **Example 2:**
  ```
  arg0: 3340747536
  arg1: 48
  arg2: 61
  arg3: 1041011
  arg4: 0
  arg5: 307
  arg6: 7896464
  arg7: 234
  arg8: 40
  arg9: 2
  arg10: ListContainer([])
  ```

  **Example 3:**
  ```
  arg0: 3340747536
  arg1: 50
  arg2: 26147
  arg3: 1041011
  arg4: 575
  arg5: 316
  arg6: 8487802
  arg7: 44
  arg8: 40
  arg9: 3
  arg10: ListContainer([])
  ```

## 5. Decode Failures & Unknown Methods

### Partial Decode Failures

| Method | Calls | Decoded | Failed | Rate |
|---|---|---|---|---|
| `Avatar.onChatMessage` | 37 | 35 | 2 | 94.6% |

### Methods with Suspicious Values

- **`Avatar.activateAirSupport`**: squadronID: very large: 210454438513; squadronID: very large: 760210252401; squadronID: very large: 1309966066289; squadronID: very large: 1859721880177; squadronID: very large: 2409477694065
- **`Avatar.beginOwnerlessTracers`**: arg2: very large: 210454438513; arg2: very large: 760210252401; arg2: very large: 1309966066289; arg2: very large: 1859721880177; arg2: very large: 2409477694065
- **`Avatar.deactivateAirSupport`**: squadronID: very large: 210454438513; squadronID: very large: 760210252401; squadronID: very large: 1309966066289; squadronID: very large: 1859721880177; squadronID: very large: 2409477694065
- **`Avatar.endOwnerlessTracers`**: arg2: very large: 210454438513; arg2: very large: 760210252401; arg2: very large: 1309966066289; arg2: very large: 1859721880177; arg2: very large: 2409477694065
- **`Avatar.onAchievementEarned`**: arg0: very large: 806569048; arg1: very large: 4277330864; arg0: very large: 806839011; arg1: very large: 4273136560; arg0: very large: 806471823
- **`Avatar.onArenaStateReceived`**: arenaUniqueId: very large: 4471079909201971
- **`Avatar.onChatMessage`**: arg0: very large: 940739859; arg0: very large: 940489968; arg0: very large: 806406716; arg0: very large: 806471823; arg0: very large: 806720509
- **`Avatar.onConnected`**: artilleryAmmoId: very large: 3339698960; airSupportAmmoId: very large: 4279140112
- **`Avatar.onOwnerChanged`**: ownerId: very large: 806471823
- **`Avatar.receiveArtilleryShots`**: arg0[].paramsID: very large: 4159685424; arg0[].paramsID: very large: 4173316912; arg0[].paramsID: very large: 4171219664; arg0[].paramsID: very large: 4193239504; arg0[].paramsID: very large: 4277126096
- **`Avatar.receiveDepthChargesPacks`**: arg0[].paramsID: very large: 4182655984
- **`Avatar.receiveExplosions`**: arg0[].paramsID: very large: 4265591248; arg0[].paramsID: very large: 4269785392; arg0[].paramsID: very large: 4279222608; arg0[].paramsID: very large: 4278174032; arg0[].paramsID: very large: 4277126096
- **`Avatar.receivePlaneProjectilePack`**: arg0[].bombParamsId: very large: 4182655984; arg0[].squadronId: very large: 210454438555; arg0[].bombParamsId: very large: 4268704528; arg0[].squadronId: very large: 210454438513; arg0[].squadronId: very large: 760210252401
- **`Avatar.receiveShellInfo`**: arg0: very large: 3340747536; arg0: very large: 3339698960; arg0: very large: 4260348368; arg0: very large: 4278174032; arg0: very large: 4292854768
- **`Avatar.receiveTorpedoes`**: arg0[].paramsID: very large: 4170597200; arg0[].skinID: very large: 3550361424; arg0[].paramsID: very large: 4234560304; arg0[].skinID: very large: 3655218992; arg0[].paramsID: very large: 4251336912
- **`Avatar.receive_CommonCMD`**: playerId: very large: 806471823; playerId: very large: 806449305; playerId: very large: 806416425; playerId: very large: 940523857; playerId: very large: 940489968
- **`Avatar.receive_addMinimapSquadron`**: arg0: very large: 141734961793; arg2: very large: 3343318832; arg0: very large: 210454438555; arg2: very large: 3346955600; arg0: very large: 210454438513
- **`Avatar.receive_addSquadron`**: arg0: very large: 3343318832; arg0: very large: 3346955600; arg0: very large: 4279140112; arg6: very large: 9817068105; arg0: very large: 4287037136
- **`Avatar.receive_changeState`**: arg0: very large: 141734961793; arg0: very large: 210454438555; arg0: very large: 210454438513; arg0: very large: 760210252401; arg0: very large: 1309966066289
- **`Avatar.receive_deactivateSquadron`**: arg0: very large: 210454438555; arg0: very large: 141734961793; arg0: very large: 210454438513; arg0: very large: 760210252401; arg0: very large: 1309966066289
- **`Avatar.receive_planeDeath`**: arg0: very large: 210454438513; arg0: very large: 760210252401; arg0: very large: 1309966066289; arg0: very large: 1859721880177; arg0: very large: 2409477694065
- **`Avatar.receive_removeMinimapSquadron`**: arg0: very large: 210454438555; arg0: very large: 141734961793; arg0: very large: 210454438513; arg0: very large: 760210252401; arg0: very large: 141734961775
- **`Avatar.receive_removeSquadron`**: arg0: very large: 210454438555; arg0: very large: 141734961793; arg0: very large: 210454438513; arg0: very large: 760210252401; arg0: very large: 141734961775
- **`Avatar.receive_resetWaypoints`**: arg0: very large: 141734961793; arg0: very large: 210454438555; arg0: very large: 210454438513; arg0: very large: 760210252401; arg0: very large: 1309966066289
- **`Avatar.receive_squadronHealth`**: arg0: very large: 141734961793; arg0: very large: 210454438555; arg0: very large: 210454438513; arg0: very large: 760210252401; arg0: very large: 1309966066289
- **`Avatar.receive_squadronPlanesHealth`**: arg0: very large: 141734961793; arg0: very large: 210454438555; arg0: very large: 210454438513; arg1: very large: 9817068105; arg1: very large: 18407002697
- **`Avatar.receive_squadronVisibilityChanged`**: arg0: very large: 210454438513; arg0: very large: 760210252401; arg0: very large: 1309966066289; arg0: very large: 1859721880177; arg0: very large: 2409477694065
- **`Avatar.receive_stopManeuvering`**: squadronId: very large: 210454438555; squadronId: very large: 141734961793; squadronId: very large: 210454438513; squadronId: very large: 760210252401; squadronId: very large: 1309966066289
- **`Avatar.receive_updateMinimapSquadron`**: arg0: very large: 141734961793; arg0: very large: 210454438555; arg0: very large: 210454438513; arg0: very large: 760210252401; arg0: very large: 141734961775
- **`Avatar.receive_updateSquadron`**: arg0: very large: 141734961793; arg0: very large: 210454438555; arg0: very large: 210454438513; arg0: very large: 760210252401; arg0: very large: 141734961775
- **`Avatar.updateMinimapVisionInfo`**: arg0[].packedData: very large: 538532649; arg0[].packedData: very large: 538533083; arg0[].packedData: very large: 538532832; arg0[].packedData: very large: 538590209; arg0[].packedData: very large: 538590427
- **`Avatar.updateOwnerlessAuraState`**: arg2: very large: 210454438513; arg2: very large: 760210252401; arg2: very large: 1309966066289; arg2: very large: 1859721880177; arg2: very large: 2409477694065
- **`Vehicle.kill`**: arg2: very large: 4229939408; arg2: very large: 4159685424; arg2: very large: 3340747536; arg2: very large: 4189045712; arg2: very large: 4279222608
- **`Vehicle.receiveHitLocationStateChange`**: arg1: very large: 20482932; arg1: very large: 49154852; arg1: very large: 32771034; arg1: very large: 32648123; arg1: very large: 32418716
- **`Vehicle.setAmmoForWeapon`**: ammoParamsId: very large: 4255105360; ammoParamsId: very large: 4193239504; ammoParamsId: very large: 4145005392; ammoParamsId: very large: 4173316912; ammoParamsId: very large: 4282369008
