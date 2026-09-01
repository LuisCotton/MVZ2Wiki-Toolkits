local p = {}

local dataCache

local function loadData()
    if dataCache then
        return dataCache
    end
    local ok, data = pcall(mw.loadJsonData, 'Spawns.json')
    if not ok or type(data) ~= 'table' then
        local title = mw.title.new('Spawns.json')
        if not title or not title.exists then
            return nil
        end
        ok, data = pcall(mw.text.jsonDecode, title:getContent() or '')
        if not ok or type(data) ~= 'table' then
            return nil
        end
    end
    dataCache = data.entries or data
    return dataCache
end

local function valueOrDefault(value, default)
    if value == nil or value == '' then
        return default
    end
    return value
end

local function link(name)
    return '[[' .. name .. ']]'
end

local function monsterLink(entry)
    if entry.id == 'undead_flying_object_blitz' then
        return '[[飞碟闪电战|不死飞行物（飞碟闪电战）]]'
    end
    return link(entry.name or entry.id or '')
end

local function terrainText(terrain)
    local result = {'陆路'}
    if type(terrain) == 'table' then
        if terrain.water then
            table.insert(result, '水路')
        end
        if terrain.air then
            table.insert(result, '空路')
        end
        if terrain.excludedTags then
            if terrain.excludedTags == 'day' then
                table.insert(result, '白天不生成')
            else
                table.insert(result, '排除标签：' .. terrain.excludedTags)
            end
        end
    end
    return table.concat(result, '、')
end

local function weightText(weight)
    if type(weight) ~= 'table' or weight.base == nil then
        return '/'
    end
    local text = tostring(valueOrDefault(weight.base, ''))
    if weight.decreaseStart ~= nil or weight.decreaseEnd ~= nil or weight.decreasePerFlag ~= nil then
        text = text .. string.format(
            '，于第%s面旗帜开始降低，于第%s面旗帜停止降低，每面旗帜降低%s',
            valueOrDefault(weight.decreaseStart, '?'),
            valueOrDefault(weight.decreaseEnd, '?'),
            valueOrDefault(weight.decreasePerFlag, '?')
        )
    end
    return text
end

local function previewText(preview)
    if type(preview) == 'table' and preview.variant ~= nil then
        return '变体预览: ' .. tostring(preview.variant)
    end
    if type(preview) == 'table' then
        return tostring(valueOrDefault(preview.count, 1))
    end
    return '1'
end

local ufoAreas = {
    '敌方不死飞行物（红）只生成在没有其他不死飞行物的右四列任意格子上，玩家方则左四列',
    '不死飞行物（绿）在可偷取的器械和障碍物数量超过3时生成在没有其他不死飞行物的格子上',
    '不死飞行物（蓝）和不死飞行物（彩）会生成在任意没有其他不死飞行物的格子上',
}

local ufoBlitzAreas = {
    '敌方不死飞行物（红）只生成在没有其他不死飞行物的右四列任意格子上，玩家方则左四列',
    '不死飞行物（绿）在可偷取的器械和障碍物超过3时生成在没有其他不死飞行物的格子上',
    '不死飞行物（蓝）和不死飞行物（彩）会生成在任意没有其他不死飞行物的格子上',
}

local function normalRow(entry)
    return '|-\n'
        .. '| ' .. monsterLink(entry) .. ' || '
        .. tostring(valueOrDefault(entry.level, '')) .. ' || '
        .. tostring(valueOrDefault(entry.minWave, 1)) .. ' || '
        .. weightText(entry.weight) .. '|| '
        .. terrainText(entry.terrain) .. ' || '
        .. previewText(entry.preview) .. ' '
end

local function ufoRows(entry, areas)
    return '|-\n'
        .. '| rowspan="3" | ' .. monsterLink(entry) .. ' || rowspan="3" | '
        .. tostring(valueOrDefault(entry.level, ''))
        .. (entry.id == 'undead_flying_object' and '（每5波出现一次）' or '')
        .. ' || rowspan="3" | '
        .. tostring(valueOrDefault(entry.minWave, 1))
        .. ' || rowspan="3" | '
        .. weightText(entry.weight)
        .. '|| ' .. areas[1] .. ' || rowspan="3" | ' .. previewText(entry.preview) .. ' \n'
        .. '|-\n'
        .. '|' .. areas[2] .. '\n'
        .. '|-\n'
        .. '|' .. areas[3]
end

local function rowFor(entry)
    if entry.id == 'undead_flying_object' then
        return ufoRows(entry, ufoAreas)
    elseif entry.id == 'undead_flying_object_blitz' then
        return ufoRows(entry, ufoBlitzAreas)
    end
    return normalRow(entry)
end

function p.getSpawns(frame)
    local data = loadData()
    if not data then
        return '错误：无法加载 [[Spawns.json]]'
    end

    local result = {
        '{| class="wikitable"',
        '|-',
        '! 怪物名称 !! 占用点数 !! 最早生成波数 !! 生成权重 !! 可生成区域 !! 出怪预览个数',
    }
    for _, entry in ipairs(data) do
        table.insert(result, rowFor(entry))
    end
    table.insert(result, '|}')
    return table.concat(result, '\n')
end

return p