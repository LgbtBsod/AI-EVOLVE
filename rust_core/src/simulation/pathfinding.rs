// Pathfinding module - L3 Simulation core
//! Grid pathfinding: binary-heap A*, Jump Point Search, Dijkstra flow field.
//!
//! Semantics (mirrored exactly by the Python twin in `src/gameplay/pathfinding.py`):
//! - grid `width x height`, row-major `costs`: 0 = blocked, 1..=255 = cost of ENTERING the cell;
//! - 8-connected; orthogonal step costs `cost(dest)`, diagonal `sqrt(2) * cost(dest)`;
//! - no corner cutting: a diagonal step needs BOTH orthogonally adjacent cells passable;
//! - A* uses the octile heuristic scaled by the minimum passable cost (admissible and consistent);
//! - JPS is for grids where all passable cells share one cost; it returns the same optimal
//!   cost as A*, with the jump segments expanded cell by cell;
//! - the flow field is Dijkstra from the target over the reversed graph: `distance(x, y)` is the
//!   cost of walking from (x, y) to the target.
//!
//! Every float operation and every tie-break (heap key `(f, h, index)`, neighbour order `DIRS`)
//! is the same as in the Python twin, so both produce identical paths and distances.

use std::cmp::Ordering;
use std::collections::BinaryHeap;

pub const SQRT_2: f64 = std::f64::consts::SQRT_2;

/// Neighbour order (also the tie-break order): orthogonals first, then diagonals.
pub const DIRS: [(i32, i32); 8] = [
    (1, 0),
    (0, 1),
    (-1, 0),
    (0, -1),
    (1, 1),
    (-1, 1),
    (-1, -1),
    (1, -1),
];

pub type Cell = (i32, i32);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Algorithm {
    Auto,
    AStar,
    Jps,
}

impl Algorithm {
    pub fn parse(name: &str) -> Result<Self, String> {
        match name {
            "auto" => Ok(Self::Auto),
            "astar" => Ok(Self::AStar),
            "jps" => Ok(Self::Jps),
            other => Err(format!("unknown algorithm {other:?}: expected one of (\"auto\", \"astar\", \"jps\")")),
        }
    }
}

/// Borrowed view of a cost grid.
#[derive(Debug, Clone, Copy)]
pub struct CostGrid<'a> {
    width: i32,
    height: i32,
    costs: &'a [u8],
    /// Smallest non-zero cost (0 when nothing is passable).
    min_cost: u8,
    /// All passable cells share one cost.
    uniform: bool,
}

impl<'a> CostGrid<'a> {
    pub fn new(width: usize, height: usize, costs: &'a [u8]) -> Result<Self, String> {
        let cells = width.checked_mul(height).ok_or("grid is too large")?;
        if costs.len() != cells {
            return Err(format!("costs has {} cells, expected {}", costs.len(), cells));
        }
        if width > i32::MAX as usize / 2 || height > i32::MAX as usize / 2 || cells >= u32::MAX as usize {
            return Err("grid is too large".to_string());
        }
        let mut min_cost = 0u8;
        let mut uniform = true;
        for &c in costs {
            if c == 0 {
                continue;
            }
            if min_cost == 0 {
                min_cost = c;
            } else if c != min_cost {
                uniform = false;
                min_cost = min_cost.min(c);
            }
        }
        Ok(Self { width: width as i32, height: height as i32, costs, min_cost, uniform })
    }

    pub fn width(&self) -> i32 {
        self.width
    }

    pub fn height(&self) -> i32 {
        self.height
    }

    pub fn is_uniform(&self) -> bool {
        self.uniform
    }

    #[inline]
    fn idx(&self, x: i32, y: i32) -> usize {
        y as usize * self.width as usize + x as usize
    }

    #[inline]
    fn cell(&self, i: usize) -> Cell {
        ((i % self.width as usize) as i32, (i / self.width as usize) as i32)
    }

    /// Cost of entering (x, y); 0 = blocked or out of bounds.
    #[inline]
    pub fn cost(&self, x: i32, y: i32) -> u8 {
        if x < 0 || y < 0 || x >= self.width || y >= self.height {
            0
        } else {
            self.costs[self.idx(x, y)]
        }
    }

    #[inline]
    pub fn passable(&self, x: i32, y: i32) -> bool {
        self.cost(x, y) != 0
    }

    /// Is the step (x, y) -> (x+dx, y+dy) legal (no corner cutting)?
    #[inline]
    pub fn can_step(&self, x: i32, y: i32, dx: i32, dy: i32) -> bool {
        if !self.passable(x + dx, y + dy) {
            return false;
        }
        dx == 0 || dy == 0 || (self.passable(x + dx, y) && self.passable(x, y + dy))
    }
}

/// Octile distance scaled by `min_cost` (lower bound of the path cost).
#[inline]
fn octile(dx: i32, dy: i32, min_cost: f64) -> f64 {
    let (dx, dy) = (dx.abs() as f64, dy.abs() as f64);
    let (lo, hi) = if dx < dy { (dx, dy) } else { (dy, dx) };
    min_cost * (hi - lo + lo * SQRT_2)
}

/// Open-list entry; the heap pops the smallest `(f, h, index)`.
#[derive(Clone, Copy)]
struct Open {
    f: f64,
    h: f64,
    idx: u32,
}

impl PartialEq for Open {
    fn eq(&self, other: &Self) -> bool {
        self.cmp(other) == Ordering::Equal
    }
}

impl Eq for Open {}

impl PartialOrd for Open {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Open {
    fn cmp(&self, other: &Self) -> Ordering {
        // reversed: BinaryHeap is a max-heap
        other
            .f
            .total_cmp(&self.f)
            .then_with(|| other.h.total_cmp(&self.h))
            .then_with(|| other.idx.cmp(&self.idx))
    }
}

fn reconstruct(grid: &CostGrid, parent: &[u32], goal: usize) -> Vec<Cell> {
    let mut path = Vec::new();
    let mut cur = goal as u32;
    while cur != u32::MAX {
        path.push(grid.cell(cur as usize));
        cur = parent[cur as usize];
    }
    path.reverse();
    path
}

/// Binary-heap A* with the octile heuristic.
#[derive(Debug, Default, Clone, Copy)]
pub struct AStar;

impl AStar {
    pub fn new() -> Self {
        Self
    }

    /// Optimal path from `start` to `goal` (both included); empty when there is none.
    pub fn find_path(&self, grid: &CostGrid, start: Cell, goal: Cell) -> Vec<Cell> {
        if !grid.passable(start.0, start.1) || !grid.passable(goal.0, goal.1) {
            return Vec::new();
        }
        if start == goal {
            return vec![start];
        }
        let n = grid.width as usize * grid.height as usize;
        let s = grid.idx(start.0, start.1);
        let t = grid.idx(goal.0, goal.1);
        let min_cost = grid.min_cost as f64;
        let mut g = vec![f64::INFINITY; n];
        let mut parent = vec![u32::MAX; n];
        let mut closed = vec![false; n];
        let mut heap = BinaryHeap::new();
        g[s] = 0.0;
        let h0 = octile(start.0 - goal.0, start.1 - goal.1, min_cost);
        heap.push(Open { f: h0, h: h0, idx: s as u32 });
        while let Some(Open { idx, .. }) = heap.pop() {
            let cur = idx as usize;
            if closed[cur] {
                continue;
            }
            closed[cur] = true;
            if cur == t {
                return reconstruct(grid, &parent, t);
            }
            let (cx, cy) = grid.cell(cur);
            let gc = g[cur];
            for &(dx, dy) in DIRS.iter() {
                let (nx, ny) = (cx + dx, cy + dy);
                let c = grid.cost(nx, ny);
                if c == 0 {
                    continue;
                }
                let ni = grid.idx(nx, ny);
                if closed[ni] {
                    continue;
                }
                let step = if dx != 0 && dy != 0 {
                    if !grid.passable(nx, cy) || !grid.passable(cx, ny) {
                        continue;
                    }
                    SQRT_2
                } else {
                    1.0
                };
                let ng = gc + step * c as f64;
                if ng < g[ni] {
                    g[ni] = ng;
                    parent[ni] = cur as u32;
                    let hh = octile(nx - goal.0, ny - goal.1, min_cost);
                    heap.push(Open { f: ng + hh, h: hh, idx: ni as u32 });
                }
            }
        }
        Vec::new()
    }
}

/// Jump Point Search for uniform-cost grids (strict no-corner-cutting rule).
///
/// With "a diagonal step needs both orthogonal cells" a diagonal move has no forced
/// neighbours; a straight move has one per side: the side cell (x, y+s) when (x-dx, y+s) is a
/// wall (plus the diagonal past it). Lengths are in cells: the uniform cost does not change
/// which path is best.
#[derive(Debug, Default, Clone, Copy)]
pub struct Jps;

impl Jps {
    pub fn new() -> Self {
        Self
    }

    /// Next jump point from `from` along (dx, dy), or `None`.
    fn jump(grid: &CostGrid, from: Cell, dx: i32, dy: i32, goal: Cell) -> Option<Cell> {
        let (mut x, mut y) = from;
        if dy == 0 {
            loop {
                if !grid.passable(x + dx, y) {
                    return None;
                }
                x += dx;
                if (x, y) == goal {
                    return Some((x, y));
                }
                if (!grid.passable(x - dx, y + 1) && grid.passable(x, y + 1))
                    || (!grid.passable(x - dx, y - 1) && grid.passable(x, y - 1))
                {
                    return Some((x, y));
                }
            }
        }
        if dx == 0 {
            loop {
                if !grid.passable(x, y + dy) {
                    return None;
                }
                y += dy;
                if (x, y) == goal {
                    return Some((x, y));
                }
                if (!grid.passable(x + 1, y - dy) && grid.passable(x + 1, y))
                    || (!grid.passable(x - 1, y - dy) && grid.passable(x - 1, y))
                {
                    return Some((x, y));
                }
            }
        }
        loop {
            if !grid.can_step(x, y, dx, dy) {
                return None;
            }
            x += dx;
            y += dy;
            if (x, y) == goal {
                return Some((x, y));
            }
            if Self::jump(grid, (x, y), dx, 0, goal).is_some() || Self::jump(grid, (x, y), 0, dy, goal).is_some() {
                return Some((x, y));
            }
        }
    }

    /// Optimal path from `start` to `goal`; the grid must be uniform-cost (checked by the caller).
    pub fn find_path(&self, grid: &CostGrid, start: Cell, goal: Cell) -> Vec<Cell> {
        if !grid.passable(start.0, start.1) || !grid.passable(goal.0, goal.1) {
            return Vec::new();
        }
        if start == goal {
            return vec![start];
        }
        let n = grid.width as usize * grid.height as usize;
        let s = grid.idx(start.0, start.1);
        let t = grid.idx(goal.0, goal.1);
        let mut g = vec![f64::INFINITY; n];
        let mut parent = vec![u32::MAX; n];
        let mut closed = vec![false; n];
        let mut heap = BinaryHeap::new();
        g[s] = 0.0;
        let h0 = octile(start.0 - goal.0, start.1 - goal.1, 1.0);
        heap.push(Open { f: h0, h: h0, idx: s as u32 });
        let mut dirs: Vec<(i32, i32)> = Vec::with_capacity(8);
        while let Some(Open { idx, .. }) = heap.pop() {
            let cur = idx as usize;
            if closed[cur] {
                continue;
            }
            closed[cur] = true;
            if cur == t {
                break;
            }
            let (cx, cy) = grid.cell(cur);
            dirs.clear();
            if parent[cur] == u32::MAX {
                dirs.extend_from_slice(&DIRS);
            } else {
                let (px, py) = grid.cell(parent[cur] as usize);
                let dx = (cx > px) as i32 - (cx < px) as i32;
                let dy = (cy > py) as i32 - (cy < py) as i32;
                if dx != 0 && dy != 0 {
                    dirs.extend_from_slice(&[(dx, 0), (0, dy), (dx, dy)]);
                } else if dy == 0 {
                    dirs.push((dx, 0));
                    for sd in [1, -1] {
                        if !grid.passable(cx - dx, cy + sd) && grid.passable(cx, cy + sd) {
                            dirs.push((0, sd));
                            dirs.push((dx, sd));
                        }
                    }
                } else {
                    dirs.push((0, dy));
                    for sd in [1, -1] {
                        if !grid.passable(cx + sd, cy - dy) && grid.passable(cx + sd, cy) {
                            dirs.push((sd, 0));
                            dirs.push((sd, dy));
                        }
                    }
                }
            }
            let gc = g[cur];
            for &(dx, dy) in dirs.iter() {
                let Some((jx, jy)) = Self::jump(grid, (cx, cy), dx, dy, goal) else {
                    continue;
                };
                let j = grid.idx(jx, jy);
                if closed[j] {
                    continue;
                }
                let steps = (jx - cx).abs().max((jy - cy).abs()) as f64;
                let ng = gc + steps * if dx != 0 && dy != 0 { SQRT_2 } else { 1.0 };
                if ng < g[j] {
                    g[j] = ng;
                    parent[j] = cur as u32;
                    let hh = octile(jx - goal.0, jy - goal.1, 1.0);
                    heap.push(Open { f: ng + hh, h: hh, idx: j as u32 });
                }
            }
        }
        if !closed[t] {
            return Vec::new();
        }
        // expand the jump segments into a cell-by-cell path
        let jumps = reconstruct(grid, &parent, t);
        let mut path = vec![jumps[0]];
        for pair in jumps.windows(2) {
            let ((mut ax, mut ay), (bx, by)) = (pair[0], pair[1]);
            let (sx, sy) = ((bx > ax) as i32 - (bx < ax) as i32, (by > ay) as i32 - (by < ay) as i32);
            while (ax, ay) != (bx, by) {
                ax += sx;
                ay += sy;
                path.push((ax, ay));
            }
        }
        path
    }
}

/// Path from `start` to `goal`. `Err` for `Algorithm::Jps` on a non-uniform grid.
pub fn find_path(grid: &CostGrid, start: Cell, goal: Cell, algorithm: Algorithm) -> Result<Vec<Cell>, String> {
    if algorithm == Algorithm::Jps && !grid.is_uniform() {
        return Err("jps needs a uniform-cost grid (all passable cells share one cost)".to_string());
    }
    let use_jps = algorithm == Algorithm::Jps || (algorithm == Algorithm::Auto && grid.is_uniform());
    Ok(if use_jps { Jps.find_path(grid, start, goal) } else { AStar.find_path(grid, start, goal) })
}

/// Dijkstra flow field: distance to the target from every cell, next step on demand.
#[derive(Debug, Clone)]
pub struct FlowField {
    width: i32,
    height: i32,
    target: Cell,
    costs: Vec<u8>,
    dist: Vec<f64>,
}

impl FlowField {
    /// Dijkstra from `target` over the reversed graph (cost of ENTERING cells on the way to it).
    pub fn compute(grid: &CostGrid, target: Cell) -> Self {
        let n = grid.width as usize * grid.height as usize;
        let mut dist = vec![f64::INFINITY; n];
        if grid.passable(target.0, target.1) {
            let t = grid.idx(target.0, target.1);
            dist[t] = 0.0;
            let mut done = vec![false; n];
            // min-heap of (distance, index): Open with h = 0 gives the same (d, idx) order
            let mut heap = BinaryHeap::new();
            heap.push(Open { f: 0.0, h: 0.0, idx: t as u32 });
            while let Some(Open { f: d, idx, .. }) = heap.pop() {
                let cur = idx as usize;
                if done[cur] {
                    continue;
                }
                done[cur] = true;
                let (x, y) = grid.cell(cur);
                let cost_here = grid.costs[cur] as f64;
                for &(dx, dy) in DIRS.iter() {
                    // the move (x-dx, y-dy) -> (x, y)
                    let (px, py) = (x - dx, y - dy);
                    if !grid.passable(px, py) {
                        continue;
                    }
                    let pi = grid.idx(px, py);
                    if done[pi] {
                        continue;
                    }
                    let nd = if dx != 0 && dy != 0 {
                        if !grid.passable(px, y) || !grid.passable(x, py) {
                            continue;
                        }
                        d + SQRT_2 * cost_here
                    } else {
                        d + 1.0 * cost_here
                    };
                    if nd < dist[pi] {
                        dist[pi] = nd;
                        heap.push(Open { f: nd, h: 0.0, idx: pi as u32 });
                    }
                }
            }
        }
        Self { width: grid.width, height: grid.height, target, costs: grid.costs.to_vec(), dist }
    }

    pub fn width(&self) -> i32 {
        self.width
    }

    pub fn height(&self) -> i32 {
        self.height
    }

    pub fn target(&self) -> Cell {
        self.target
    }

    /// Cost of the cheapest path from (x, y) to the target; `None` if unreachable/blocked/outside.
    pub fn distance(&self, x: i32, y: i32) -> Option<f64> {
        if x < 0 || y < 0 || x >= self.width || y >= self.height {
            return None;
        }
        let d = self.dist[y as usize * self.width as usize + x as usize];
        if d.is_finite() {
            Some(d)
        } else {
            None
        }
    }

    /// Distances by rows; `f64::INFINITY` = no path.
    pub fn distances(&self) -> &[f64] {
        &self.dist
    }

    fn grid(&self) -> CostGrid<'_> {
        CostGrid {
            width: self.width,
            height: self.height,
            costs: &self.costs,
            min_cost: 0,
            uniform: false,
        }
    }

    /// The step (dx, dy) that leads to the target along a cheapest path; `None` at the target,
    /// on a wall, outside, or when there is no path.
    pub fn direction(&self, x: i32, y: i32) -> Option<(i32, i32)> {
        match self.distance(x, y) {
            None => return None,
            Some(d) if d == 0.0 => return None,
            _ => {}
        }
        let grid = self.grid();
        let mut best = f64::INFINITY;
        let mut out = None;
        for &(dx, dy) in DIRS.iter() {
            let (nx, ny) = (x + dx, y + dy);
            let c = grid.cost(nx, ny);
            if c == 0 {
                continue;
            }
            let Some(dn) = self.distance(nx, ny) else { continue };
            let v = if dx != 0 && dy != 0 {
                if !grid.passable(nx, y) || !grid.passable(x, ny) {
                    continue;
                }
                dn + SQRT_2 * c as f64
            } else {
                dn + 1.0 * c as f64
            };
            if v < best {
                best = v;
                out = Some((dx, dy));
            }
        }
        out
    }

    /// Flat `[dx0, dy0, dx1, dy1, ...]` by rows; `(0, 0)` = no step.
    pub fn directions(&self) -> Vec<i32> {
        let mut out = Vec::with_capacity(self.dist.len() * 2);
        for y in 0..self.height {
            for x in 0..self.width {
                let (dx, dy) = self.direction(x, y).unwrap_or((0, 0));
                out.push(dx);
                out.push(dy);
            }
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Parse an ASCII map: '#' wall, '.' cost 1, digits 2..9 cost.
    fn parse(rows: &[&str]) -> (usize, usize, Vec<u8>) {
        let h = rows.len();
        let w = rows[0].len();
        let mut costs = Vec::new();
        for r in rows {
            for ch in r.chars() {
                costs.push(match ch {
                    '#' => 0,
                    '.' | 'S' | 'G' => 1,
                    d => d.to_digit(10).unwrap() as u8,
                });
            }
        }
        (w, h, costs)
    }

    fn cost_of(grid: &CostGrid, path: &[Cell]) -> f64 {
        let mut total = 0.0;
        for pair in path.windows(2) {
            let (a, b) = (pair[0], pair[1]);
            let (dx, dy) = (b.0 - a.0, b.1 - a.1);
            assert!(DIRS.contains(&(dx, dy)), "not neighbours: {a:?} -> {b:?}");
            assert!(grid.can_step(a.0, a.1, dx, dy), "illegal step {a:?} -> {b:?}");
            total += if dx != 0 && dy != 0 { SQRT_2 } else { 1.0 } * grid.cost(b.0, b.1) as f64;
        }
        total
    }

    struct Lcg(u64);

    impl Lcg {
        fn next(&mut self) -> u64 {
            self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            self.0 >> 33
        }
        fn below(&mut self, n: u64) -> u64 {
            self.next() % n
        }
    }

    #[test]
    fn open_grid_is_a_straight_diagonal_then_line() {
        let (w, h, costs) = parse(&["......", "......", "......", "......"]);
        let grid = CostGrid::new(w, h, &costs).unwrap();
        for algo in [Algorithm::AStar, Algorithm::Jps, Algorithm::Auto] {
            let path = find_path(&grid, (0, 0), (5, 3), algo).unwrap();
            assert_eq!(path.first(), Some(&(0, 0)));
            assert_eq!(path.last(), Some(&(5, 3)));
            assert!((cost_of(&grid, &path) - (2.0 + 3.0 * SQRT_2)).abs() < 1e-9);
        }
    }

    #[test]
    fn wall_with_a_gap() {
        let (w, h, costs) = parse(&["..#..", "..#..", ".....", "..#..", "..#.."]);
        let grid = CostGrid::new(w, h, &costs).unwrap();
        let path = find_path(&grid, (0, 0), (4, 0), Algorithm::AStar).unwrap();
        assert!(path.contains(&(2, 2)), "must pass through the gap: {path:?}");
        let jps = find_path(&grid, (0, 0), (4, 0), Algorithm::Jps).unwrap();
        assert!((cost_of(&grid, &path) - cost_of(&grid, &jps)).abs() < 1e-9);
    }

    #[test]
    fn unreachable_blocked_and_trivial() {
        let (w, h, costs) = parse(&["..#..", "..#..", "..#.."]);
        let grid = CostGrid::new(w, h, &costs).unwrap();
        assert!(find_path(&grid, (0, 0), (4, 0), Algorithm::Auto).unwrap().is_empty());
        assert!(find_path(&grid, (2, 0), (0, 0), Algorithm::Auto).unwrap().is_empty()); // blocked start
        assert!(find_path(&grid, (0, 0), (2, 1), Algorithm::Auto).unwrap().is_empty()); // blocked goal
        assert!(find_path(&grid, (-1, 0), (0, 0), Algorithm::Auto).unwrap().is_empty()); // outside
        assert!(find_path(&grid, (0, 0), (9, 9), Algorithm::Auto).unwrap().is_empty());
        assert_eq!(find_path(&grid, (1, 1), (1, 1), Algorithm::Auto).unwrap(), vec![(1, 1)]);
    }

    #[test]
    fn no_corner_cutting() {
        let (w, h, costs) = parse(&["S#", "#G"]);
        let grid = CostGrid::new(w, h, &costs).unwrap();
        assert!(find_path(&grid, (0, 0), (1, 1), Algorithm::AStar).unwrap().is_empty());
        assert!(find_path(&grid, (0, 0), (1, 1), Algorithm::Jps).unwrap().is_empty());
        let (w, h, costs) = parse(&["S#", ".G"]);
        let grid = CostGrid::new(w, h, &costs).unwrap();
        for algo in [Algorithm::AStar, Algorithm::Jps] {
            let path = find_path(&grid, (0, 0), (1, 1), algo).unwrap();
            assert_eq!(path, vec![(0, 0), (0, 1), (1, 1)]);
        }
    }

    #[test]
    fn weighted_detour_when_cheaper() {
        let (w, h, costs) = parse(&[".....", ".999.", "....."]);
        let grid = CostGrid::new(w, h, &costs).unwrap();
        let path = find_path(&grid, (0, 1), (4, 1), Algorithm::Auto).unwrap();
        assert!(!path.contains(&(2, 1)), "should go around the expensive cells: {path:?}");
        assert!((cost_of(&grid, &path) - (2.0 + 2.0 * SQRT_2)).abs() < 1e-9);
        assert!(find_path(&grid, (0, 1), (4, 1), Algorithm::Jps).is_err());
    }

    #[test]
    fn jps_matches_astar_on_random_uniform_grids() {
        let mut rng = Lcg(12345);
        let mut checked = 0;
        for _ in 0..600 {
            let (w, h) = (3 + rng.below(30) as usize, 3 + rng.below(30) as usize);
            let density = rng.below(41);
            let costs: Vec<u8> = (0..w * h).map(|_| if rng.below(100) < density { 0 } else { 2 }).collect();
            let grid = CostGrid::new(w, h, &costs).unwrap();
            let free: Vec<usize> = (0..w * h).filter(|&i| costs[i] != 0).collect();
            if free.len() < 2 {
                continue;
            }
            for _ in 0..3 {
                let a = grid.cell(free[rng.below(free.len() as u64) as usize]);
                let b = grid.cell(free[rng.below(free.len() as u64) as usize]);
                let pa = AStar.find_path(&grid, a, b);
                let pj = Jps.find_path(&grid, a, b);
                assert_eq!(pa.is_empty(), pj.is_empty(), "reachability differs {a:?} -> {b:?}");
                if !pa.is_empty() {
                    assert!((cost_of(&grid, &pa) - cost_of(&grid, &pj)).abs() < 1e-6, "cost differs {a:?} -> {b:?}");
                    checked += 1;
                }
            }
        }
        assert!(checked > 500);
    }

    #[test]
    fn flow_field_distances_directions_and_astar_agree() {
        let mut rng = Lcg(99);
        for _ in 0..200 {
            let (w, h) = (3 + rng.below(20) as usize, 3 + rng.below(20) as usize);
            let costs: Vec<u8> = (0..w * h)
                .map(|_| if rng.below(100) < 25 { 0 } else { 1 + rng.below(4) as u8 })
                .collect();
            let grid = CostGrid::new(w, h, &costs).unwrap();
            let free: Vec<usize> = (0..w * h).filter(|&i| costs[i] != 0).collect();
            if free.len() < 2 {
                continue;
            }
            let target = grid.cell(free[rng.below(free.len() as u64) as usize]);
            let field = FlowField::compute(&grid, target);
            assert_eq!(field.distance(target.0, target.1), Some(0.0));
            assert_eq!(field.direction(target.0, target.1), None);
            for &i in &free {
                let start = grid.cell(i);
                let path = AStar.find_path(&grid, start, target);
                match field.distance(start.0, start.1) {
                    None => assert!(path.is_empty()),
                    Some(d) => {
                        assert!((d - cost_of(&grid, &path)).abs() < 1e-6);
                        // follow the field
                        let (mut c, mut total, mut guard) = (start, 0.0, 0);
                        while c != target {
                            let (dx, dy) = field.direction(c.0, c.1).expect("a step");
                            assert!(grid.can_step(c.0, c.1, dx, dy));
                            total += if dx != 0 && dy != 0 { SQRT_2 } else { 1.0 } * grid.cost(c.0 + dx, c.1 + dy) as f64;
                            c = (c.0 + dx, c.1 + dy);
                            guard += 1;
                            assert!(guard <= w * h);
                        }
                        assert!((total - d).abs() < 1e-6);
                    }
                }
            }
        }
    }

    #[test]
    fn flow_field_on_a_blocked_target_is_empty() {
        let (w, h, costs) = parse(&["..#", "..."]);
        let grid = CostGrid::new(w, h, &costs).unwrap();
        let field = FlowField::compute(&grid, (2, 0));
        assert_eq!(field.distance(0, 0), None);
        assert_eq!(field.direction(0, 0), None);
        assert!(field.directions().iter().all(|&v| v == 0));
        let outside = FlowField::compute(&grid, (9, 9));
        assert_eq!(outside.distance(1, 1), None);
    }

    #[test]
    fn bad_input_is_an_error() {
        assert!(CostGrid::new(3, 3, &[1u8; 8]).is_err());
        assert!(Algorithm::parse("dijkstra").is_err());
        let empty = CostGrid::new(0, 0, &[]).unwrap();
        assert!(find_path(&empty, (0, 0), (0, 0), Algorithm::Auto).unwrap().is_empty());
    }
}
