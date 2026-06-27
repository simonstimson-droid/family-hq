tell application "Reminders"
    if not (exists list "Latitude 2026") then
        make new list with properties {name:"Latitude 2026"}
    end if
    
    set lr to list "Latitude 2026"
    
    -- 16 July
    set d1 to current date
    set {year of d1, month of d1, day of d1, hours of d1, minutes of d1, seconds of d1} to {2026, 7, 16, 9, 0, 0}
    make new reminder in lr with properties {name:"Check tent & camping gear condition", body:"Check tent seams, poles, pegs, groundsheet. Any tears? Buy replacements.", due date:d1}
    
    -- 17 July
    set d2 to current date
    set {year of d2, month of d2, day of d2, hours of d2, minutes of d2, seconds of d2} to {2026, 7, 17, 9, 0, 0}
    make new reminder in lr with properties {name:"Buy camping essentials for Latitude Festival", body:"Wet wipes, sunscreen, insect repellent, hand sanitiser, bin bags, dry shampoo", due date:d2}
    
    -- 20 July
    set d3 to current date
    set {year of d3, month of d3, day of d3, hours of d3, minutes of d3, seconds of d3} to {2026, 7, 20, 9, 0, 0}
    make new reminder in lr with properties {name:"Download Latitude app & save tickets", body:"Save tickets offline. Download the app for the line-up and schedule.", due date:d3}
    
    -- 21 July
    set d4 to current date
    set {year of d4, month of d4, day of d4, hours of d4, minutes of d4, seconds of d4} to {2026, 7, 21, 9, 0, 0}
    make new reminder in lr with properties {name:"Pack clothes for Latitude Festival", body:"Wellies, waterproof jacket, warm layers, sun hat, comfy shoes, fancy dress/costumes for kids", due date:d4}
    make new reminder in lr with properties {name:"Pack first aid bits - blister plasters etc", body:"Plasters, blister pads, paracetamol, antihistamines, after-bite, sunscreen", due date:d4}
    make new reminder in lr with properties {name:"Pack chairs, blankets & tarp", body:"Camping chairs, picnic blankets, tarp for under tent, camping beds", due date:d4}
    
    -- 22 July
    set d5 to current date
    set {year of d5, month of d5, day of d5, hours of d5, minutes of d5, seconds of d5} to {2026, 7, 22, 9, 0, 0}
    make new reminder in lr with properties {name:"Charge power banks, phones, speakers, torches", body:"Full charge all power banks, Bluetooth speakers, LED torches, glow sticks", due date:d5}
    make new reminder in lr with properties {name:"Pack toiletries & first aid", body:"Wet wipes, loo roll, first aid supplies, any meds, hand sanitiser, dry shampoo", due date:d5}
    make new reminder in lr with properties {name:"Prepare food & snacks", body:"Crisps, cereal bars, biscuits, fruit. Breakfast bits (cereal, long-life milk). Tea/coffee/sugar.", due date:d5}
    make new reminder in lr with properties {name:"Pack torches & glow sticks for kids", body:"Head torches, glow sticks, LED wristbands, spare batteries", due date:d5}
end tell

return "Done"
