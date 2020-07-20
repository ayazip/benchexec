// This file is part of BenchExec, a framework for reliable benchmarking:
// https://github.com/sosy-lab/benchexec
//
// SPDX-FileCopyrightText: 2019-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

import React from "react";
import "../../node_modules/react-vis/dist/style.css";
import {
  XYPlot,
  MarkSeries,
  VerticalGridLines,
  HorizontalGridLines,
  XAxis,
  YAxis,
  Hint,
  DecorativeAxis,
  makeWidthFlexible,
} from "react-vis";
import {
  getRunSetName,
  setParam,
  getHashSearch,
  isNil,
  getFirstVisibles,
} from "../utils/utils";

const scalingOptions = {
  linear: "Linear",
  logarithmic: "Logarithmic",
};

const resultsOptions = {
  all: "All",
  correct: "Correct",
};

const lineOptions = [
  2,
  3,
  4,
  5,
  6,
  7,
  8,
  9,
  10,
  100,
  1000,
  10000,
  100000,
  1000000,
  10000000,
  100000000,
];

const defaultValues = {
  scaling: scalingOptions.linear,
  results: resultsOptions.correct,
  line: 10,
  UIDesign: 1,
};

export default class ScatterPlot extends React.Component {
  constructor(props) {
    super(props);

    this.state = this.setup();
    this.maxX = "";
    this.minX = "";
    this.lineCount = 1;
  }

  setup() {
    const defaultName =
      getRunSetName(this.props.tools[0]) + " " + this.props.columns[0][1];

    let { results, scaling, toolX, toolY, columnX, columnY, line, UIDesign } = {
      ...defaultValues,
      ...getHashSearch(),
    };

    let dataX, dataY, areAllColsHidden;

    if (isNil(toolX) || isNil(columnX)) {
      const [firstVisibleTool, firstVisibleColumn] = getFirstVisibles(
        this.props.tools,
        this.props.hiddenCols,
      );
      areAllColsHidden = firstVisibleTool === undefined;
      toolX = firstVisibleTool;
      dataX = `${firstVisibleTool}-${firstVisibleColumn}`;
    } else {
      areAllColsHidden = false;
      dataX = `${toolX}-${columnX}`;
    }

    if (isNil(toolY) || isNil(columnY)) {
      const [firstVisibleTool, firstVisibleColumn] = getFirstVisibles(
        this.props.tools,
        this.props.hiddenCols,
      );
      areAllColsHidden = firstVisibleTool === undefined;
      toolY = firstVisibleTool;
      dataY = `${firstVisibleTool}-${firstVisibleColumn}`;
    } else {
      areAllColsHidden = false;
      dataY = `${toolY}-${columnY}`;
    }

    let out = {
      dataX,
      dataY,
      results,
      scaling,
      toolX: 0,
      toolY: 0,
      line: line || 10,
      columnX: 1,
      columnY: 1,
      nameX: defaultName,
      nameY: defaultName,
      value: false,
      height: window.innerHeight,
      areAllColsHidden,
      UIDesign,
    };

    if (dataX && !areAllColsHidden) {
      out = { ...out, ...this.extractAxisInfoByName(dataX, "X") };
    }
    if (dataY && !areAllColsHidden) {
      out = { ...out, ...this.extractAxisInfoByName(dataY, "Y") };
    }
    return out;
  }

  // ----------------------resizer-------------------------------
  componentDidMount() {
    window.addEventListener("resize", this.updateDimensions);
    window.addEventListener("popstate", this.refreshUrlState);
  }

  componentWillUnmount() {
    window.removeEventListener("resize", this.updateDimensions);
    window.removeEventListener("popstate", this.refreshUrlState);
  }

  updateDimensions = () => {
    this.setState({
      height: window.innerHeight,
    });
  };

  refreshUrlState = () => {
    this.setState(this.setup());
  };

  // --------------------rendering-----------------------------
  renderColumns = () => {
    return this.props.tools.map((runset, i) => (
      <optgroup key={"runset" + i} label={getRunSetName(runset)}>
        {runset.columns.map((column, j) => {
          return !this.props.hiddenCols[i].includes(column.colIdx) ? (
            <option
              key={i + column.display_title}
              value={i + "-" + column.colIdx}
              name={column.display_title}
            >
              {column.display_title}
            </option>
          ) : null;
        })}
      </optgroup>
    ));
  };

  renderData = () => {
    let array = [];
    this.hasInvalidLog = false;

    if (!this.state.areAllColsHidden) {
      this.props.table.forEach((row) => {
        const resX = row.results[this.state.toolX];
        const resY = row.results[this.state.toolY];
        const x = resX.values[this.state.columnX].raw;
        const y = resY.values[this.state.columnY].raw;
        const hasValues =
          x !== undefined && x !== null && y !== undefined && y !== null;
        const areOnlyCorrectResults =
          this.state.results === resultsOptions.correct;

        if (
          hasValues &&
          (!areOnlyCorrectResults ||
            (areOnlyCorrectResults &&
              resX.category === "correct" &&
              resY.category === "correct"))
        ) {
          const isLogAndInvalid =
            this.state.scaling === scalingOptions.logarithmic &&
            (x <= 0 || y <= 0);

          if (isLogAndInvalid) {
            this.hasInvalidLog = true;
          } else {
            array.push({
              x,
              y,
              info: this.props.getRowName(row),
            });
          }
        }
      });
    }

    this.setMinMaxValues(array);

    this.lineCount = array.length;
    this.dataArray = array;
  };

  setMinMaxValues = (array) => {
    const xValues = array.map((el) => el.x);
    const yValues = array.map((el) => el.y);

    this.maxX = this.findMaxValue(xValues);
    this.maxY = this.findMaxValue(yValues);
    this.minX = this.findMinValue(xValues);
    this.minY = this.findMinValue(yValues);
  };

  findMaxValue = (values) => {
    const max = Math.max(...values);
    return max < 3 ? 3 : max;
  };

  findMinValue = (values) => {
    const min = Math.min(...values);
    return min > 2 ? 1 : min;
  };

  renderSettingOptions = (options, name) =>
    Object.values(options).map((option) => (
      <option value={option} key={option} name={option + " " + name}>
        {option + " " + name}
      </option>
    ));

  // ------------------------handeling----------------------------
  handleType = (tool, column) => {
    const colType = this.props.tools[tool].columns[column].type;
    if (colType === "text" || colType === "status") {
      return "ordinal";
    } else {
      return this.state.scaling === scalingOptions.logarithmic
        ? "log"
        : "linear";
    }
  };

  extractAxisInfoByName = (val, axis) => {
    let [toolIndex, colIdx] = val.split("-");
    return {
      [`data${axis}`]: val,
      [`tool${axis}`]: toolIndex,
      [`column${axis}`]: colIdx,
      [`name${axis}`]: this.props.tools[toolIndex].columns.find(
        (col) => col.colIdx === parseInt(colIdx),
      ).display_title,
    };
  };

  setAxis = (ev, axis) => {
    this.array = [];
    let [tool, column] = ev.target.value.split("-");
    column = column.replace("___", "-");
    setParam({ [`tool${axis}`]: tool, [`column${axis}`]: column });
  };

  setLine = (ev) => {
    setParam({ line: ev.target.value });
  };

  setScaling = (ev) => {
    setParam({ scaling: ev.target.value });
  };

  setResults = (ev) => {
    setParam({ results: ev.target.value });
  };

  setUI = (ev) => {
    setParam({ UIDesign: ev.target.value });
  };

  render() {
    this.renderData();
    const isLinear = this.state.scaling === scalingOptions.linear;
    const FlexibleXYPlot = makeWidthFlexible(XYPlot);
    const showColon = [1, 2].includes(parseInt(this.state.UIDesign));
    const areSelectionsOnTheRight =
      this.state.UIDesign > 3 && this.state.UIDesign < 6;

    return (
      <>
        <div className={"scatterPlot" + this.state.UIDesign}>
          {areSelectionsOnTheRight ? (
            <div className="settings-container">
              <div className="setting">
                <span className="setting-label">
                  X-Axis{showColon ? ":" : ""}
                </span>
                <select
                  className="setting-select"
                  name="X-Axis"
                  value={this.state.dataX}
                  onChange={(ev) => this.setAxis(ev, "X")}
                >
                  {this.renderColumns()}
                </select>
              </div>
              <div className="setting">
                <span className="setting-label">
                  Y-Axis{showColon ? ":" : ""}
                </span>
                <select
                  className="setting-select"
                  name="Y-Axis"
                  value={this.state.dataY}
                  onChange={(ev) => this.setAxis(ev, "Y")}
                >
                  {this.renderColumns()}
                </select>
              </div>
              <div className="setting">
                <span className="setting-label">
                  Scaling{showColon ? ":" : ""}
                </span>
                <select
                  className="setting-select"
                  name="Scaling"
                  value={this.state.scaling}
                  onChange={this.setScaling}
                >
                  {this.renderSettingOptions(scalingOptions, "Scale")}
                </select>
              </div>
              <div className="setting">
                <span className="setting-label">
                  Results{showColon ? ":" : ""}
                </span>
                <select
                  className="setting-select"
                  name="Results"
                  value={this.state.results}
                  onChange={this.setResults}
                >
                  {this.renderSettingOptions(resultsOptions, "Results")}
                </select>
              </div>
              <div className="setting">
                <span className="setting-label">
                  Aux. Lines{showColon ? ":" : ""}
                </span>
                <select
                  className="setting-select"
                  name="Aux. Lines"
                  value={this.state.line}
                  onChange={this.setLine}
                >
                  {this.renderSettingOptions(lineOptions, "")}
                </select>
              </div>
            </div>
          ) : (
            <div className="settings-container">
              <div className="settings-subcontainer">
                <div className="setting">
                  <span className="setting-label">
                    X-Axis{showColon ? ":" : ""}
                  </span>
                  <select
                    className="setting-select"
                    name="X-Axis"
                    value={this.state.dataX}
                    onChange={(ev) => this.setAxis(ev, "X")}
                  >
                    {this.renderColumns()}
                  </select>
                </div>
                <div className="setting">
                  <span className="setting-label">
                    Y-Axis{showColon ? ":" : ""}
                  </span>
                  <select
                    className="setting-select"
                    name="Y-Axis"
                    value={this.state.dataY}
                    onChange={(ev) => this.setAxis(ev, "Y")}
                  >
                    {this.renderColumns()}
                  </select>
                </div>
              </div>
              <div className="settings-subcontainer">
                <div className="setting">
                  <span className="setting-label">
                    Scaling{showColon ? ":" : ""}
                  </span>
                  <select
                    className="setting-select"
                    name="Scaling"
                    value={this.state.scaling}
                    onChange={this.setScaling}
                  >
                    {this.renderSettingOptions(scalingOptions, "Scale")}
                  </select>
                </div>
                <div className="setting">
                  <span className="setting-label">
                    Results{showColon ? ":" : ""}
                  </span>
                  <select
                    className="setting-select"
                    name="Results"
                    value={this.state.results}
                    onChange={this.setResults}
                  >
                    {this.renderSettingOptions(resultsOptions, "Results")}
                  </select>
                </div>
                <div className="setting">
                  <span className="setting-label">
                    Aux. Lines{showColon ? ":" : ""}
                  </span>
                  <select
                    className="setting-select"
                    name="Aux. Lines"
                    value={this.state.line}
                    onChange={this.setLine}
                  >
                    {this.renderSettingOptions(lineOptions, "")}
                  </select>
                </div>
              </div>
            </div>
          )}
          <FlexibleXYPlot
            className="scatterPlot__plot"
            height={this.state.height - 200}
            margin={{ left: 90 }}
            yType={this.handleType(this.state.toolY, this.state.columnY)}
            xType={this.handleType(this.state.toolX, this.state.columnX)}
            xDomain={
              this.handleType(this.state.toolX, this.state.columnX) !==
              "ordinal"
                ? [this.minX, this.maxX]
                : null
            }
            yDomain={
              this.handleType(this.state.toolY, this.state.columnY) !==
              "ordinal"
                ? [this.minY, this.maxY]
                : null
            }
          >
            <VerticalGridLines
              yType={this.handleType(this.state.toolY, this.state.columnY)}
              xType={this.handleType(this.state.toolX, this.state.columnX)}
            />
            <HorizontalGridLines
              yType={this.handleType(this.state.toolY, this.state.columnY)}
              xType={this.handleType(this.state.toolX, this.state.columnX)}
            />

            <DecorativeAxis
              className="middle-line"
              axisStart={{
                x: isLinear ? 0 : 1,
                y: isLinear ? 0 : 1,
              }}
              axisEnd={{
                x: this.maxX > this.maxY ? this.maxX : this.maxY,
                y: this.maxX > this.maxY ? this.maxX : this.maxY,
              }}
              axisDomain={[0, 10000000000]}
              style={{
                ticks: { stroke: "#009440", opacity: 0 },
                text: {
                  stroke: "none",
                  fill: "#009440",
                  fontWeight: 600,
                  opacity: 0,
                },
              }}
            />
            <DecorativeAxis
              axisStart={{
                x: isLinear ? 0 : this.state.line,
                y: isLinear ? 0 : 1,
              }}
              axisEnd={{ x: this.maxX, y: this.maxX / this.state.line }}
              axisDomain={[0, 10000000000]}
              style={{
                ticks: { stroke: "#ADDDE1", opacity: 0 },
                text: {
                  stroke: "none",
                  fill: "#6b6b76",
                  fontWeight: 600,
                  opacity: 0,
                },
              }}
            />
            <DecorativeAxis
              axisStart={{
                x: isLinear ? 0 : 1,
                y: isLinear ? 0 : this.state.line,
              }}
              axisEnd={{ x: this.maxX, y: this.maxX * this.state.line }}
              axisDomain={[0, 10000000000]}
              style={{
                ticks: { stroke: "#ADDDE1", opacity: 0 },
                text: {
                  stroke: "none",
                  fill: "#6b6b76",
                  fontWeight: 600,
                  opacity: 0,
                },
              }}
            />
            <XAxis
              title={this.state.nameX}
              tickFormat={(value) => value}
              yType={this.handleType(this.state.toolY, this.state.columnY)}
              xType={this.handleType(this.state.toolX, this.state.columnX)}
            />
            <YAxis
              title={this.state.nameY}
              tickFormat={(value) => value}
              yType={this.handleType(this.state.toolY, this.state.columnY)}
              xType={this.handleType(this.state.toolX, this.state.columnX)}
            />
            <MarkSeries
              data={this.dataArray}
              onValueMouseOver={(datapoint, event) =>
                this.setState({ value: datapoint })
              }
              onValueMouseOut={(datapoint, event) =>
                this.setState({ value: null })
              }
            />
            {this.state.value ? <Hint value={this.state.value} /> : null}
          </FlexibleXYPlot>
          {this.state.areAllColsHidden ? (
            <div className="plot__noresults">No columns to show!</div>
          ) : (
            this.lineCount === 0 && (
              <div className="plot__noresults">
                No {this.state.results === resultsOptions.correct && "correct"}{" "}
                results
                {this.props.table.length > 0 && " with valid data points"}
                {this.hasInvalidLog &&
                  " (negative values are not shown in logarithmic plot)"}
              </div>
            )
          )}
        </div>
        <div
          style={{
            textAlign: "center",
            padding: ".5em",
            fontSize: "1.5em",
            backgroundColor: "#71bcff",
          }}
        >
          <span
            style={{
              paddingRight: "1em",
            }}
          >
            UI Design Selection:
          </span>
          <select
            style={{
              fontSize: "1em",
            }}
            name="UI"
            value={this.state.UIDesign}
            onChange={this.setUI}
          >
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3</option>
            <option value="4">4</option>
            <option value="5">5</option>
            <option value="6">6</option>
            <option value="7">7</option>
            <option value="8">8</option>
            <option value="9">9</option>
          </select>
        </div>
      </>
    );
  }
}
