// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
const DirectorRules = (() => {
  const R = {
    tiers: {
      safety: 1,
      progress: 2,
      handin: 3,
      pickup: 3,
      errand: 3,
      area: 3,
      next: 4,
      chore: null,
    },
    run: {
      typical: 500,
      least: 200,
      most: 1500,
      steps: 8,
      hop: 100,
      follow: 0.5,
    },
    reach: {
      giver: 0.2,
      way: 0.04,
      visit: 0.2,
      corridor: 0.06,
      area: 0.2,
      walked_away: 1,
      left: 0.06,
      back: 0.3,
      pass: 0.4,
      choose: 0.2,
    },
    cost: {
      far: 100000,
      ridden: 1200,
    },
    along: {
      reach: 50,
    },
    no_flap: {
      hold: 30,
      choose_for: 30,
      left_for: 30,
    },
    claims: {
      reckoned: 0.065,
      order: 0.024,
    },
    sure: {
      least: 0.8,
      off: 0.2,
      own: 1,
      pace: 0.5,
    },
    camps: {
      least_s: 300,
      least_n: 6,
      window: 900,
      busy: 0.5,
      quiet: 0.8,
      tapped: 2,
      empty: 0.25,
      move: 3,
      stays: 900,
      gap_most: 10,
    },
    director: {
      at_once: 1,
      cooldown: 90,
      closed_quiet: 900,
      linger: 60,
      break_for: 20,
      dry: 240,
      left_for: 45,
      page_for: 15,
      breaks: ["handed_in", "objective_done", "quest_done", "arrived", "town"],
    },
    words: {
      progress_giver: "{lost} can wait: its giver stays here, and you're {n} kills from finishing {won}.",
      progress_giver_one: "{lost} can wait: its giver stays here, and you're 1 kill from finishing {won}.",
      progress_giver_more: "{lost} can wait: its giver stays here, and you need {n} more for {won}.",
      progress_step: "{lost} can wait: you're {n} kills from finishing {won}.",
      progress_step_one: "{lost} can wait: you're 1 kill from finishing {won}.",
      progress_step_more: "{lost} can wait: you need {n} more for {won}.",
      handin: "{wonNpc} is close by, so you hand in {won} now and save a walk back for it later.",
      handins: "{n} quests are ready to hand in close by, so you hand them in now and save a walk back later.",
      pickup: "{wonNpc} is close by, so you pick up {won} now and save a walk back for it later.",
      handin_here: "{won} is ready to hand in close by, so you hand it in now and save a walk back later.",
      pickup_here: "The giver of {won} is close by, so you pick it up now and save a walk back later.",
      area: "You're in the area for {won}, so you do that quest now and save a walk back later.",
      errand: "{wonNpc} is close by, so you stop there now and save a walk back later.",
      chose: "You headed for {won}, so the guide goes there with you.",
      wait_giver: "{lost} can wait: you come back past {lostNpc} later anyway.",
      wait_area: "{lost} can wait: you come back this way later anyway.",
      walked: "You walked away from {lost}, so the guide goes on with {won}.",
      only: "Nothing else is left to do now, so the guide takes you to {wonNpc}.",
      back: "The guide goes back to this parked quest, since every other step is done or waiting.",
      later: "Later",
      put_off: "You put this chore off until you're next in town.",
      put_off_said: "You put off {chore} until you're next in town.",
      trace_start: "The plan loaded, and its first step to do leads.",
      trace_plan: "The step before is done, so the plan's next step leads.",
      trace_left: "The step that led can't lead any more, so the plan's step leads.",
      trace_progress: "You're working this step, so it leads.",
      trace_stop: "Every step of the plan is done, so nothing leads.",
      hearth: "Your Hearthstone takes you to {town}, which saves you about {n} minutes.",
      hearth_one: "Your Hearthstone takes you to {town}, which saves you about a minute.",
      train_way: "{spells} are trained on the way.",
      train_way_one: "{spells} is trained on the way.",
      put_off_npc: "You put this chore off until you're next near {npc}.",
      put_off_said_npc: "You put off {chore} until you're next near {npc}.",
      progress_giver_thing: "{lost} can wait: its giver stays here, and you're {n} {things} from finishing them.",
      progress_giver_thing_one: "{lost} can wait: its giver stays here, and you're 1 {thing} from finishing it.",
      progress_step_thing: "{lost} can wait: you're {n} {things} from finishing them.",
      progress_step_thing_one: "{lost} can wait: you're 1 {thing} from finishing it.",
      pass: "{place} first. {nearer}'s quests come later in the plan.",
      pass_s: "{place} first. {nearer}' quests come later in the plan.",
      busy: "Other players seem to be camping the spawns for {won}. {lost} is a better option.",
      busy_thing: "Other players seem to be camping the {things}. {lost} is a better option.",
      put_off_town: "You put this chore off until you're next in {town}.",
      put_off_said_town: "You put off {chore} until you're next in {town}.",
      put_off_place: "You put this chore off until you're next in {place}.",
      put_off_said_place: "You put off {chore} until you're next in {place}.",
      core_now: "{spells} are core: train now.",
      core_now_one: "{spells} is core: train now.",
      only_wait: "{lost} waits, because {why}. Until then, the guide takes you to {wonNpc}.",
    },
    quiet: {
      words: ["handin", "handins", "pickup", "handin_here", "pickup_here", "area", "wait_giver", "wait_area", "progress_giver", "progress_giver_one", "progress_giver_more", "progress_step", "progress_step_one", "progress_step_more", "progress_giver_thing", "progress_giver_thing_one", "progress_step_thing", "progress_step_thing_one", "errand"],
    },
    drift: {
      replan: 1,
      extra: 1,
      chore: 0.5,
      order: 1,
      off: 180,
      off_most: 2,
      nudge: 4,
      again: 4,
    },
    asks: {
      levelup: 3,
      classquest: 2.5,
      nextzone: 2,
      drift: 1,
    },
    next: {
      ahead: 3,
    },
    lines: {
      next_news: "You're level {level}, so {zone} is at your level now.",
      next_news_zeppelin: "You're level {level}, so {zone} is at your level now, if you fancy a zeppelin and a longer journey.",
      next_news_boat: "You're level {level}, so {zone} is at your level now, if you fancy a boat and a longer journey.",
      next_also: "So is {zone}.",
      next_far_zeppelin: "{zone} is open too, if you fancy a zeppelin and a longer journey.",
      next_far_boat: "{zone} is open too, if you fancy a boat and a longer journey.",
      next_leads: "A few quests here end up in {zone} anyway.",
      next_leads_one: "One quest here ends up in {zone} anyway.",
      next_ask: "Replan for only those, so you can be on your way?",
      next_ask_one: "Replan for only that one, so you can be on your way?",
      next_none: "Nothing here leads to {zone}, so replan in the Index whenever you want to move on.",
      left_work: "You were working on {quest} with {n} left to do. After that you {next}.",
      left_work_last: "You were working on {quest} with {n} left to do, the last step of the plan.",
      left_go: "You were on your way to {doing}. After that you {next}.",
      left_go_last: "You were on your way to {doing}, the last step of the plan.",
      replan_asked: "The Index is writing a new plan from where you stand. When the plan is ready, the Index asks you to /reload.",
      replan_zone_asked: "The Index is writing a plan for the quests that lead to {zone}. When the plan is ready, the Index asks you to /reload.",
      background_said: "You put {quest} in the background until your {skill} reaches {need}.",
      background_back: "{quest} is back in your steps, since your {skill} reached {need}.",
      putback_here_said: "{thing} is back where it was in your plan.",
      putback_visit_said: "{thing} is back in your plan for when you're next in town.",
      putback_visit_said_town: "{thing} is back in your plan for your next visit to {town}.",
      putback_visit_said_npc: "{thing} is back in your plan for your next visit to {npc}.",
      putback_visit_said_place: "{thing} is back in your plan for your next visit to {place}.",
      putback_place_said: "{thing} is back at its place in your plan.",
      class_news: "Your {class} class quest {chain} is open now. It teaches you {unlocks}.",
      class_news_plain: "Your {class} class quest {chain} is open now.",
      class_ask: "Start an epic that plans the whole class quest for you?",
      class_asked: "The Index is writing a class quest epic for {chain}. When the plan is ready, the Index asks you to /reload.",
    },
    phrases: {
      do_P: "pick up {name} from {npc}",
      do_P_alone: "pick up {name}",
      do_T: "hand in {name} to {npc}",
      do_T_alone: "hand in {name}",
      do_O: "work on {name}",
      do_D: "run {name}",
    },
    heads: {
      drawer_later: "Next time we're in town",
      drawer_later_town: "Next time we're in {town}",
      drawer_later_npc: "Next time we're near {npc}",
      drawer_later_place: "Next time we're in {place}",
      drawer_parked: "Parked quests, back when you unpark them",
      drawer_skipped: "Chores skipped for good",
      drawer_skipped_level: "Chores skipped until your next level",
      drawer_background: "Quests in the background, back when your skill is up",
      drawer_row_background: "{quest}: {skill} {have} of {need}",
      drawer_short: "Quests in your log, planned when your skill is up",
      class_quest: "Class quest",
      bag_slot: "1 Free bag slot",
      bag_slots: "{n} Free bag slots",
      camp_restock: "Buy wood for campfire kits",
      camp_left_none: "No wood or kits left for a camp",
      camp_left_one: "Wood for 1 more camp in your bags",
      camp_left: "Wood for {n} more camps in your bags",
      camp_wood: "{n} {wood}",
      camp_wood_tool: "{n} {wood} and a {tool}",
      camp_buy: "Buy {buy} at {npc}",
      camp_short: "Buying {buy} costs {cost}, and you have {have}",
      no_vendor: "No vendor of yours in reach sells {thing}",
    },
    buttons: {
      replan: "Replan",
      background: "Background",
      close_tip: "Closing this is always fine.",
      replan_tip: "Replan asks the Index for a new plan that fits the character's spot now.",
      zone_tip: "Replan asks the Index for a plan of only the quests that lead on to the next zone.",
      drawer_tip: "The steps put off, parked or skipped, and when each one comes back. The arrow on a row puts that step back in the plan.",
      background_tip: "Background sets this quest aside until the skill reaches its level. The quest comes back by itself.",
      background_row_tip: "A click on this step shows its Background key, which sets the quest aside until the skill reaches its level.",
      background_copy_tip: "Copies the line that sets this quest aside in game until the skill reaches its level. The quest comes back by itself.",
      putback_here_tip: "This puts {thing} back where it was in the plan, since the character is still close by.",
      putback_visit_tip: "This puts {thing} back in the plan for when the character is next in town.",
      putback_visit_tip_town: "This puts {thing} back in the plan for the next visit to {town}.",
      putback_visit_tip_npc: "This puts {thing} back in the plan for the next visit to {npc}.",
      putback_visit_tip_place: "This puts {thing} back in the plan for the next visit to {place}.",
      putback_place_tip: "This puts {thing} back at its place in the plan.",
      start: "Start",
      class_tip: "Start asks the Index for a class quest epic, a plan of every step of the class quest in order.",
      class_close_tip: "Closing this dismisses the to-do for good. Zone epics still put the class quest first.",
    },
    pools: {
      drift: ["Heroes who stick to the map end up in very short ballads. Replan when you want the next verse.", "The prophecy didn't mention this bit, which is the best thing a prophecy can say about anyone. Replan to update the prophecy.", "The plan was a suggestion, and you've made a counter-offer. Replan to settle on terms.", "Nobody ever bought a round for someone who followed the instructions. Replan when you're thirsty for more.", "The bards of Goldshire have abandoned rhyme to keep up with you. Replan to give the bards a chorus.", "Legends are mostly people who went the wrong way on purpose. Replan for the next chapter.", "Your deeds have run out of margin. Replan for a fresh page.", "Maps are drawn by people who stayed at home. Replan to draw your own.", "The bronze dragons have started taking notes on you. Replan to give the dragons a tidy copy.", "You took the road less travelled. Replan for the road back.", "Somewhere an innkeeper is telling your story and getting the route wrong. Replan to put the route right.", "The goblins of Booty Bay couldn't have priced this detour. Replan for an honest quote on the rest.", "Off the map is where the good stories live. Replan when you want to visit the plot.", "You wrote your own quest. Replan to fit your quest into the book.", "The quest givers can wait, and some have been waiting since the Second War. Replan when you're ready.", "History is written by people who wandered off. Replan to write the next part."],
      stay: ["Or stay and turn over every last rock. {here} has plenty of rocks.", "Or stay until {here} runs out of things to ask of you. That may take a while.", "Or stay and talk to every villager twice. Somebody in {here} has to.", "Or stay and check that barrel too. {here} has been saving the barrel for you.", "Or stay and finish your chores. Evil can wait, and in {here} evil usually does.", "Or stay and collect every single spoon. {here} notices a missing spoon.", "Or stay and see to the last exclamation marks. {here} still has a few.", "Or stay a while. The world isn't ending, whatever the posters in {here} say.", "Or stay and finish {here} properly. Bards are paid by the verse.", "Or stay and take your time. {here} isn't going anywhere, being a place."],
    },
    back: {
      order: ["town", "npc", "place"],
    },
    restock: {
      camp_low: 2,
      camp_stock: 5,
    },
    guide: {
      arrive: 8,
      board: 15,
      landed: 150,
      with_giver: 40,
      ways: ["way", "alt", "ez", "hw"],
      closer_by: 0.9,
    },
    lead: {
      epic: 1,
      nav: 1,
      loop: 1,
      prof: 2,
    },
    badges: {
      mobs: ["#00b5ff", "#ff3392", "#cc8800", "#59ffe9", "#ffb2a6", "#d5a6ff", "#738ae6", "#29c1cc", "#ccaf85", "#e695b5", "#a6c3ff", "#ff9c59", "#a6e7ff", "#ff00dd", "#e66b00", "#ff80e5"],
    },
    codes: ["progress_giver", "progress_giver_one", "progress_giver_more", "progress_step", "progress_step_one", "progress_step_more", "handin", "handins", "pickup", "handin_here", "pickup_here", "area", "errand", "chose", "wait_giver", "wait_area", "walked", "only", "back", "later", "put_off", "put_off_said", "trace_start", "trace_plan", "trace_left", "trace_progress", "trace_stop", "hearth", "hearth_one", "train_way", "train_way_one", "put_off_npc", "put_off_said_npc", "progress_giver_thing", "progress_giver_thing_one", "progress_step_thing", "progress_step_thing_one", "pass", "pass_s", "busy", "busy_thing", "put_off_town", "put_off_said_town", "put_off_place", "put_off_said_place", "core_now", "core_now_one", "only_wait"],
  };

  const tier = (kind) => (Object.hasOwn(R.tiers, kind) ? R.tiers[kind] : null);
  function wins(a, b) {
    const ta = tier(a.kind), tb = tier(b.kind);
    if (ta === null) return false;
    return tb === null || ta < tb;
  }
  const held = (run) => Math.max(R.run.least, Math.min(R.run.most, run));
  function run(lengths) {
    const walks = (lengths ?? []).filter((l) => typeof l === "number" && l > 0);
    if (walks.length === 0) return R.run.typical;
    const list = walks.filter((l) => l >= R.run.hop).sort((x, y) => x - y);
    const n = list.length;
    if (n === 0) return R.run.least;
    return held(n % 2 === 1 ? list[(n - 1) / 2] : (list[n / 2 - 1] + list[n / 2]) / 2);
  }
  function reach(name, run) {
    if (!Object.hasOwn(R.reach, name)) return null;
    const t = R.run.typical;
    return R.reach[name] * t * Math.pow(held(run ?? t) / t, R.run.follow);
  }
  const dist = (ax, ay, bx, by) => Math.sqrt((ax - bx) ** 2 + (ay - by) ** 2);
  function reached(t, x, y) {
    if (Array.isArray(t.ar) && t.ar.length > 0) {
      let best = Infinity, mx = t.x, my = t.y;
      for (const p of t.ar) {
        const d = dist(p[0], p[1], x, y) - (p[2] ?? 0);
        if (d < best) { best = d; mx = p[0]; my = p[1]; }
      }
      return [Math.max(0, best), mx, my];
    }
    return [dist(x, y, t.x, t.y), t.ox ?? t.x, t.oy ?? t.y];
  }
  function among(t, x, y) {
    let best, bx, by, mid = null, mx, my;
    const patches = Array.isArray(t.ar) && t.ar.length > 0;
    if (patches) {
      best = Infinity; mid = Infinity;
      for (const p of t.ar) {
        const full = dist(p[0], p[1], x, y), r = p[2] ?? 0, d = full - r;
        mid = Math.min(mid, full);
        if (d < best) {
          best = d; mx = p[0]; my = p[1];
          if (d <= 0 || full <= 0) { bx = x; by = y; } else { bx = p[0] + (x - p[0]) * r / full; by = p[1] + (y - p[1]) * r / full; }
        }
      }
    } else {
      best = dist(t.x, t.y, x, y); bx = t.x; by = t.y; mx = t.x; my = t.y;
    }
    const loop = t.loop;
    if (!patches && Array.isArray(loop) && loop.length > 1) {
      for (let i = 1; i < loop.length; i++) {
        const [ax, ay] = loop[i - 1], [cx, cy] = loop[i], dx = cx - ax, dy = cy - ay, len2 = dx * dx + dy * dy;
        const u = len2 > 0 ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / len2)) : 0;
        const qx = ax + u * dx, qy = ay + u * dy, d = dist(qx, qy, x, y);
        if (d < best) { best = d; bx = qx; by = qy; }
      }
    }
    return [best, bx, by, mid ?? best, mx, my];
  }
  function here(t, x, y, run) {
    if (Array.isArray(t.hr) && t.hr.length > 0) t = { ...t, ar: [...(Array.isArray(t.ar) ? t.ar : []), ...t.hr] };
    const got = among(t, x, y);
    return got[0] <= reach("area", run) ? got : null;
  }
  function arrived(t, x, y, run) {
    const d = among(t, x, y)[0];
    if (Array.isArray(t.ar) && t.ar.length > 0) return d <= 0;
    return d <= reach("giver", run);
  }
  function along(line, px, py, first) {
    let best = Infinity, at = 0, start = 0;
    for (let k = 1; k < line.length; k++) {
      const [ax, ay] = line[k - 1], [bx, by] = line[k], size = dist(ax, ay, bx, by);
      const u = size > 0 ? Math.max(0, Math.min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / (size * size))) : 0;
      const d = dist(ax + u * (bx - ax), ay + u * (by - ay), px, py);
      if (d < best) { best = d; at = start + u * size; }
      start = start + size;
    }
    const to = Math.min(first, start);
    let done = 0, hx = line[line.length - 1][0] - line[0][0], hy = line[line.length - 1][1] - line[0][1];
    for (let k = 1; k < line.length; k++) {
      const [ax, ay] = line[k - 1], [bx, by] = line[k], size = dist(ax, ay, bx, by);
      if (done + size >= to || k === line.length - 1) {
        const u = size > 0 ? (to - done) / size : 0;
        hx = ax + u * (bx - ax) - line[0][0]; hy = ay + u * (by - ay) - line[0][1];
        break;
      }
      done = done + size;
    }
    return [best, at, start, (px - line[0][0]) * hx + (py - line[0][1]) * hy];
  }
  function passes(a, b, p, run, bends) {
    const giver = reach("giver", run), way = reach("way", run), visit = reach("visit", run);
    const dap = dist(a.x, a.y, p.x, p.y), dab = dist(a.x, a.y, b.x, b.y), dpb = dist(p.x, p.y, b.x, b.y);
    if (dab > visit && dap <= giver && dpb > giver) return true;
    if (dpb <= R.run.hop) return false;
    if (bends) {
      const line = [[a.x, a.y], ...bends.map((q) => [q[0], q[1]]), [b.x, b.y]];
      const [off, at, length, ahead] = along(line, p.x, p.y, giver);
      if (dap <= giver && length > giver && dap + dpb - length <= giver && (dap <= way || ahead >= 0)) return true;
      return at > 0 && off <= giver && length - at > giver && off + dpb - (length - at) <= giver;
    }
    const dot = (p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y);
    if (dap <= giver && dab > giver && dap + dpb - dab <= giver && (dap <= way || dot >= 0)) return true;
    if (dab <= 0 || dab >= R.cost.ridden) return false;
    const t = Math.min(1, dot / (dab * dab));
    if (t <= 0) return false;
    const dqp = dist(a.x + t * (b.x - a.x), a.y + t * (b.y - a.y), p.x, p.y), dqb = (1 - t) * dab;
    return dqp <= giver && dqb > giver && dqp + dpb - dqb <= giver;
  }
  function legWay(t, x, y) {
    let best = Infinity, out = null;
    for (const w of t.ways ?? []) {
      for (let k = 1; k < w.length; k++) {
        const [ax, ay] = w[k - 1], [bx, by] = w[k], size = dist(ax, ay, bx, by);
        const u = size > 0 ? Math.max(0, Math.min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / (size * size))) : 0;
        const d = dist(ax + u * (bx - ax), ay + u * (by - ay), x, y);
        if (d < best) { best = d; out = w.slice(k); }
      }
    }
    return best <= R.run.hop ? out : null;
  }
  function fit(first, stops, anchor, here, run) {
    const route = [first];
    if (anchor && anchor.key === first.key) anchor = null;
    for (const t of stops) if (t.key !== first.key && !(anchor && t.key === anchor.key)) route.push(t);
    if (anchor) route.push(anchor);
    let cost = 0;
    const outs = [{ x: first.ox ?? first.x, y: first.oy ?? first.y }];
    for (let k = 1; k < route.length; k++) {
      const [d, x, y] = reached(route[k], outs[k - 1].x, outs[k - 1].y);
      cost = cost + d;
      outs.push({ x, y });
    }
    const walk = (here ? [{ x: here.x, y: here.y }] : []).concat(outs), lead = walk.length - outs.length;
    const ways = [null];
    for (let j = 1; j < walk.length; j++) ways.push(legWay(route[j - lead], walk[j - 1].x, walk[j - 1].y));
    for (let k = 1; k < route.length; k++) {
      const t = route[k];
      if (!t.open) continue;
      for (let j = 1; j < k + lead; j++) {
        if (passes(walk[j - 1], walk[j], t, run, ways[j])) {
          cost = cost + 2 * dist(walk[j].x, walk[j].y, t.x, t.y);
          break;
        }
      }
    }
    return { cost, route };
  }
  function apart(t, first) {
    const [, mx, my] = reached(first, t.x, t.y);
    return dist(t.x, t.y, mx, my) > R.run.hop;
  }
  function sooner(t, first, stops, anchor, here, run) {
    const at = stops.findIndex((s) => s.key === t.key);
    const visit = at < 0 ? [] : stops.slice(0, at).filter((s) => s.open && dist(s.x, s.y, t.x, t.y) <= R.run.hop);
    for (let k = at < 0 ? stops.length : at + 1; k < stops.length; k++) {
      if (dist(stops[k].x, stops[k].y, t.x, t.y) > R.run.hop) break;
      visit.push(stops[k]);
    }
    const keys = new Set([t.key, ...visit.map((s) => s.key)]);
    const route = visit.concat([first], stops.filter((s) => !keys.has(s.key)));
    const now = t.walk + fit(t, route, anchor, here, run).cost;
    const later = first.walk + fit(first, stops, anchor, here, run).cost;
    return { now, later, yes: apart(t, first) && now < later - 1e-6 };
  }
  function mayShow(open, sinceLast, sinceClosed) {
    const d = R.director;
    return open < d.at_once && (sinceLast === null || sinceLast === undefined || sinceLast >= d.cooldown)
      && (sinceClosed === null || sinceClosed === undefined || sinceClosed >= d.closed_quiet);
  }
  function play(off, own, pace) {
    const s = R.sure, doublings = typeof pace === "number" && pace > 0 ? Math.abs(Math.log(pace) / Math.log(2)) : 0;
    return 1 + s.off * Math.max(0, off ?? 0) + s.own * Math.abs(own ?? 0) + s.pace * doublings;
  }
  function sure(kind, steps, factor) {
    if (!Object.hasOwn(R.claims, kind) || typeof steps !== "number" || steps < 0) return 0;
    return Math.pow(1 - Math.min(1, R.claims[kind] * Math.max(1, factor ?? 1)), steps);
  }
  const said = (kind, steps, factor) => sure(kind, steps, factor) >= R.sure.least;
  const filled = typeof module === "object" ? require("./words.js").fillWords : fillWords;
  const say = (key, fill) => (Object.hasOwn(R.words, key) ? filled(R.words[key], fill) : null);
  const quiet = (key) => R.quiet.words.includes(key);
  const TEXT = ["words", "lines", "phrases", "heads", "buttons"];
  const line = (part, key, fill) => (TEXT.includes(part) && Object.hasOwn(R[part], key) ? filled(R[part][key], fill) : null);
  function town(towns, inst, x, y) {
    if (!towns || !Array.isArray(towns.list) || inst === null || inst === undefined || typeof x !== "number"
        || typeof y !== "number") return null;
    const near = Number(towns.near) || 0;
    let best = Infinity, out = null;
    for (const t of towns.list) {
      if (!Array.isArray(t) || t[1] !== inst || typeof t[2] !== "number" || typeof t[3] !== "number") continue;
      const d = Math.sqrt((t[2] - x) ** 2 + (t[3] - y) ** 2);
      if (d <= near && d < best) { best = d; out = t[0]; }
    }
    return typeof out === "string" && out !== "" ? out : null;
  }
  function back(part, key, where, fill) {
    for (const name of R.back.order) {
      const v = where?.[name];
      if (v !== null && v !== undefined && v !== "" && TEXT.includes(part) && Object.hasOwn(R[part], `${key}_${name}`)) {
        return line(part, `${key}_${name}`, { ...(fill ?? {}), [name]: v });
      }
    }
    return line(part, key, fill ?? {});
  }
  function pick(name, n, fill) {
    const pool = Object.hasOwn(R.pools, name) ? R.pools[name] : null;
    if (!pool || !pool.length || !Number.isInteger(n)) return null;
    return filled(pool[(((n - 1) % pool.length) + pool.length) % pool.length], fill);
  }
  function moment(fighting, working, sinceBreak, sinceReward) {
    const d = R.director, some = (v) => v !== null && v !== undefined;
    if (fighting) return false;
    if (!working) return true;
    return (some(sinceBreak) && sinceBreak <= d.break_for) || (some(sinceReward) && sinceReward >= d.dry);
  }
  function offWeight(yards, reach) {
    if (typeof reach !== "number" || reach <= 0 || typeof yards !== "number" || yards <= reach) return 0;
    return Math.min(R.drift.off_most, yards / reach);
  }
  function drift(p) {
    const w = R.drift, q = p ?? {};
    return w.replan * (q.replan ?? 0) + w.extra * (q.extra ?? 0) + w.chore * (q.chore ?? 0) + w.order * (q.order ?? 0)
      + (q.off ?? 0) / w.off;
  }
  function nudge(points, shownAt) {
    const w = R.drift;
    if (typeof points !== "number" || points < w.nudge) return false;
    return shownAt === null || shownAt === undefined || points >= shownAt + w.again;
  }
  function slots(objs, free) {
    if (typeof free !== "number") return 0;
    const want = (objs ?? []).filter((o) => o.item && !o.finished && (o.need ?? 0) > 0 && (o.have ?? 0) === 0).length;
    return free < want ? want : 0;
  }
  const onCard = (shownKind, shownIds, kind, quest) =>
    shownKind !== "P" && kind === "O" && quest !== null && quest !== undefined && (shownIds ?? []).includes(quest);
  const spawnedNear = (spots, x, y) => (spots ?? []).some((p) => dist(p[0], p[1], x, y) <= R.along.reach);
  function ways(offQuick, offEasy, leftQuick, leftEasy, lengths) {
    const at = run(lengths), on = reach("way", at), away = reach("walked_away", at);
    if (offQuick <= on && offEasy <= on && Math.abs(leftEasy - leftQuick) <= on) return offEasy < offQuick ? "easy" : "quick";
    if (offEasy <= on && offQuick > away) return "easy";
    if (offQuick <= on && offEasy > away) return "quick";
    return "both";
  }
  function colours(rows, kept) {
    const n = rows.length, top = rows.map((_, i) => i), owner = new Map();
    const root = (i) => { while (top[i] !== i) i = top[i]; return i; };
    rows.forEach((keys, i) => keys.forEach((k) => {
      if (!owner.has(k)) { owner.set(k, i); return; }
      const a = root(i), b = root(owner.get(k));
      if (a !== b) top[Math.max(a, b)] = Math.min(a, b);
    }));
    const most = R.badges.mobs.length, groups = top.filter((_, i) => root(i) === i), place = new Map(), taken = new Set();
    for (const g of groups) {
      for (let i = g; i < n; i++) {
        if (root(i) !== g) continue;
        for (const k of rows[i]) {
          const p = kept && Object.hasOwn(kept, k) ? kept[k] : null;
          if (!place.has(g) && typeof p === "number" && p >= 1 && p <= most && !taken.has(p)) { place.set(g, p); taken.add(p); }
        }
      }
    }
    groups.forEach((g, x) => {
      if (place.has(g)) return;
      let p = null;
      for (let q = 1; q <= most && p === null; q++) if (!taken.has(q)) p = q;
      p = p ?? x % most + 1;
      place.set(g, p);
      taken.add(p);
    });
    const out = { rows: [], kept: {} };
    rows.forEach((keys, i) => {
      const p = place.get(root(i));
      out.rows.push(p);
      for (const k of keys) out.kept[k] = p;
    });
    return out;
  }
  function beacon(spots, running, held) {
    let top = null;
    for (const kind of running ?? []) {
      const t = R.lead[kind];
      if (typeof t === "number" && (top === null || t < top)) top = t;
    }
    let best = null, keep = null;
    for (const s of spots ?? []) {
      if (top === null || s.yards === null || s.yards === undefined || R.lead[s.kind] !== top) continue;
      if (!best || s.yards < best.yards) best = s;
      if (held !== null && held !== undefined && s.id === held) keep = s;
    }
    if (keep && best.yards > keep.yards * R.guide.closer_by) best = keep;
    return best ? best.id : null;
  }
  const code = (key) => R.codes.indexOf(key) + 1;

  return { table: R, tier, wins, run, reach, reached, among, here, arrived, along, passes, legWay, fit, apart, sooner, mayShow,
           play, sure, said, say, quiet, line, town, back, pick, moment, offWeight, drift, nudge, slots, onCard, spawnedNear,
           ways, colours, beacon,
           code };
})();

if (typeof module === "object") {
  module.exports = DirectorRules;
}
