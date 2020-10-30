// This file is part of BenchExec, a framework for reliable benchmarking:
// https://github.com/sosy-lab/benchexec
//
// SPDX-FileCopyrightText: 2019-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

import {
  isOkStatus,
  numericSortMethod,
  textSortMethod,
  getHashSearch,
  setHashSearch,
  getFilterParamsFromUrl,
  setFilterParamsInUrl,
  NumberFormatterBuilder,
  hasSameEntries,
  makeFilterSerializer,
  makeFilterDeserializer,
} from "../utils/utils";

describe("isStatusOk", () => {
  test("should return true if status code is 0", () => {
    expect(isOkStatus(0)).toBe(true);
  });
  test("should return true if status code is 200", () => {
    expect(isOkStatus(200)).toBe(true);
  });
  test("should return false if other integer is passed", () => {
    expect(isOkStatus(404)).toBe(false);
  });
  test("should return false if string is passed", () => {
    expect(isOkStatus("hi there")).toBe(false);
  });
  test("should return false if object is passed", () => {
    expect(isOkStatus({ a: "b" })).toBe(false);
  });
  test("should return false if nothing is passed", () => {
    expect(isOkStatus()).toBe(false);
  });
});

describe("numericSortMethod", () => {
  test("should evaluate order of objects with different values", () => {
    const bigger = { raw: 9001 };
    const smaller = { raw: 1337 };
    expect(numericSortMethod(bigger, smaller)).toBeGreaterThan(0);
    expect(numericSortMethod(smaller, bigger)).toBeLessThan(0);
  });

  test("should evaluate order of objects with same values", () => {
    const even1 = { raw: 1 };
    const even2 = { raw: 1 };
    expect(numericSortMethod(even1, even2)).toBe(0);
  });

  test("should order items without raw prop last", () => {
    const testObject = { raw: 1 };
    const objectWithoutProp = { fake: 1 };
    expect(numericSortMethod(objectWithoutProp, testObject)).toBeGreaterThan(0);
    expect(numericSortMethod(testObject, objectWithoutProp)).toBeLessThan(0);
  });

  test("should be nil safe", () => {
    const testObject = { raw: 1 };
    expect(numericSortMethod(null, testObject)).toBeGreaterThan(0);
    expect(numericSortMethod(undefined, testObject)).toBeGreaterThan(0);
    expect(numericSortMethod(testObject, null)).toBeLessThan(0);
    expect(numericSortMethod(testObject, undefined)).toBeLessThan(0);
  });
});

describe("hashRouting helpers", () => {
  describe("getHashSearch", () => {
    test("should get params as object", () => {
      const res = getHashSearch("localhost#/bla?id=1&name=benchexec");
      expect(res).toMatchObject({ id: "1", name: "benchexec" });
    });

    test("should return empty object if no params are given", () => {
      const res = getHashSearch("localhost#bla");
      expect(res).toMatchObject({});
    });

    test("should return empty object if only ? is given", () => {
      const res = getHashSearch("localhost#bla?");
      expect(res).toMatchObject({});
    });
  });

  describe("setHashSearch", () => {
    test("should translate object to queryparams", () => {
      const params = { id: "1", name: "benchexec" };
      const res = setHashSearch(params, {
        returnString: true,
        baseUrl: "localhost#table",
      });
      expect(res).toEqual("localhost#table?id=1&name=benchexec");
    });
  });
  describe("getFilterParamsFromUrl", () => {
    test("should return null if no filter set", () => {
      const res = getFilterParamsFromUrl("localhost#/bla?id=1&name=benchexec");

      expect(res).toBe(null);
    });

    test("should parse b64 encoded filters in url", () => {
      const obj = { a: "b" };
      const parsed = JSON.stringify(obj);

      const res = getFilterParamsFromUrl(
        `localhost#/bla?id=1&name=benchexec&filter=${btoa(parsed)}`,
      );

      expect(res).toStrictEqual(obj);
    });
  });

  describe("setFilterParamsFromUrl", () => {
    test("should set no filter if nullish parameter is passed", () => {
      const res = setFilterParamsInUrl(null, { returnString: true });

      expect(res).not.toContain("filter");
    });

    test("should embed filters as serialized b64 string", () => {
      const obj = { a: "b" };

      const res = setFilterParamsInUrl(obj, { returnString: true });

      expect(res).toContain(btoa(JSON.stringify(obj)));
    });
  });
});

describe("serialization", () => {
  let serializer;
  const statusValues = [
    [["true", "false", "TIMEOUT", "OOM", "false(reach)"]],
    [["true", "false", "TIMEOUT", "OOM", "false(reach)"]],
  ];
  const categoryValues = [
    [["correct ", "wrong ", "missing ", "unknown "]],
    [["correct ", "wrong ", "missing ", "unknown "]],
  ];

  const makeSelection = (selection, base) => {
    // the status column has id 0
    return base[0].filter((item) =>
      selection.every((select) => item !== select),
    );
  };
  beforeEach(() => {
    serializer = makeFilterSerializer({
      statusValues,
      categoryValues,
    });
  });

  test("should serialize id filters", () => {
    const filter = [{ id: "id", values: ["abc", "def"] }];
    const expected = "id(values(abc,def))";

    expect(serializer(filter)).toBe(expected);
  });

  test("should serialize normal value filters for one runset", () => {
    const filter = [
      { id: "0_cputime_1", value: "1223:4567" },
      { id: "0_hostname_2", value: "satu" },
    ];

    const urlencoded = escape("1223:4567");
    const expected = `0(1*cputime*(value(${urlencoded})),2*hostname*(value(satu)))`;

    expect(serializer(filter)).toBe(expected);
  });

  test("should serialize normal value filters in multiple runsets", () => {
    const filter = [
      { id: "0_cputime_1", value: "1223:4567" },
      { id: "1_cputime_1", value: ":4567" },
      { id: "0_hostname_2", value: "satu" },
      { id: "1_hostname_2", value: "tilo" },
    ];

    const urlencoded1 = escape("1223:4567");
    const urlencoded2 = escape(":4567");

    const filterRunset1 = `0(1*cputime*(value(${urlencoded1})),2*hostname*(value(satu)))`;
    const filterRunset2 = `1(1*cputime*(value(${urlencoded2})),2*hostname*(value(tilo)))`;
    const expected = `${filterRunset1},${filterRunset2}`;

    expect(serializer(filter)).toBe(expected);
  });

  test("should serialize normal value filters in multiple runsets and id filter", () => {
    const filter = [
      { id: "0_cputime_1", value: "1223:4567" },
      { id: "1_cputime_1", value: ":4567" },
      { id: "0_hostname_2", value: "satu" },
      { id: "1_hostname_2", value: "tilo" },
      { id: "id", values: ["abc", "def"] },
    ];

    const urlencoded1 = escape("1223:4567");
    const urlencoded2 = escape(":4567");

    const filterRunset1 = `0(1*cputime*(value(${urlencoded1})),2*hostname*(value(satu)))`;
    const filterRunset2 = `1(1*cputime*(value(${urlencoded2})),2*hostname*(value(tilo)))`;
    const expected = `id(values(abc,def)),${filterRunset1},${filterRunset2}`;

    expect(serializer(filter)).toBe(expected);
  });

  test("should serialize status filter correctly (notIn)", () => {
    const uncheckedBoxes = ["true", "false"];
    const selected = makeSelection(uncheckedBoxes, statusValues[0]);

    const filter = selected.map((status) => ({
      id: "0_status_0",
      value: status,
    }));

    const expected = "0(0*status*(status(notIn(true,false))))";

    expect(serializer(filter)).toBe(expected);
  });

  test("should serialize status filter correctly (in)", () => {
    const uncheckedBoxes = ["true", "false", "TIMEOUT"];
    const selected = makeSelection(uncheckedBoxes, statusValues[0]);

    const filter = selected.map((status) => ({
      id: "0_status_0",
      value: status,
    }));

    const encoded = escape("false(reach)");

    const expected = `0(0*status*(status(in(OOM,${encoded}))))`;

    expect(serializer(filter)).toBe(expected);
  });

  test("should serialize status filter correctly in multiple runsets", () => {
    const uncheckedBoxes1 = ["true", "false", "TIMEOUT"];
    const uncheckedBoxes2 = ["true", "false"];
    const selected1 = makeSelection(uncheckedBoxes1, statusValues[0]);
    const selected2 = makeSelection(uncheckedBoxes2, statusValues[0]);

    const makeStatus = (selection, runset) =>
      selection.map((status) => ({
        id: `${runset}_status_0`,
        value: status,
      }));

    const filter = [...makeStatus(selected1, 0), ...makeStatus(selected2, 1)];

    const encoded = escape("false(reach)");

    const expected1 = `0(0*status*(status(in(OOM,${encoded}))))`;
    const expected2 = `1(0*status*(status(notIn(true,false))))`;

    expect(serializer(filter)).toBe(`${expected1},${expected2}`);
  });

  test("should serialize category filter correctly (notIn)", () => {
    const uncheckedBoxes = ["unknown "];
    const selected = makeSelection(uncheckedBoxes, categoryValues[0]);

    const filter = selected.map((status) => ({
      id: "0_status_0",
      value: status,
    }));

    const expected = "0(0*status*(category(notIn(unknown))))";

    expect(serializer(filter)).toBe(expected);
  });

  test("should serialize category filter correctly (in)", () => {
    const uncheckedBoxes = ["correct ", "wrong "];
    const selected = makeSelection(uncheckedBoxes, categoryValues[0]);

    const filter = selected.map((status) => ({
      id: "0_status_0",
      value: status,
    }));

    const expected = `0(0*status*(category(in(missing,unknown))))`;

    expect(serializer(filter)).toBe(expected);
  });

  test("should serialize category filter correctly in multiple runsets", () => {
    const uncheckedBoxes1 = ["correct ", "wrong "];
    const uncheckedBoxes2 = ["unknown "];
    const selected1 = makeSelection(uncheckedBoxes1, categoryValues[0]);
    const selected2 = makeSelection(uncheckedBoxes2, categoryValues[0]);

    const makeStatus = (selection, runset) =>
      selection.map((status) => ({
        id: `${runset}_status_0`,
        value: status,
      }));

    const filter = [...makeStatus(selected1, 0), ...makeStatus(selected2, 1)];

    const expected1 = `0(0*status*(category(in(missing,unknown))))`;
    const expected2 = `1(0*status*(category(notIn(unknown))))`;

    expect(serializer(filter)).toBe(`${expected1},${expected2}`);
  });
});

describe("Filter deserialization", () => {
  let deserializer;

  const statusValues = [
    [["true", "false", "TIMEOUT", "OOM", "false(reach)"]],
    [["true", "false", "TIMEOUT", "OOM", "false(reach)"]],
  ];
  const categoryValues = [
    [["correct ", "wrong ", "missing ", "unknown "]],
    [["correct ", "wrong ", "missing ", "unknown "]],
  ];

  beforeEach(() => {
    deserializer = makeFilterDeserializer({ statusValues, categoryValues });
  });

  test("should deserialize id filter", () => {
    const string = "id(values(abc,def))";

    const expected = [{ id: "id", values: ["abc", "def"] }];

    expect(deserializer(string)).toStrictEqual(expected);
  });

  test("should deserialize normal values for one runset", () => {
    const string = "0(1*cputime*(value(%3A1234)))";

    const expected = [{ id: "0_cputime_1", value: ":1234" }];

    expect(deserializer(string)).toStrictEqual(expected);
  });

  test("should deserialize normal values for many runsets", () => {
    const string =
      "0(1*cputime*(value(%3A1234))),1(1*cputime*(value(23%3A1234)))";

    const expected = [
      { id: "0_cputime_1", value: ":1234" },
      { id: "1_cputime_1", value: "23:1234" },
    ];

    expect(deserializer(string)).toStrictEqual(expected);
  });

  test("should deserialize status filters (in)", () => {
    const string = "0(0*status*(status(in(true,false))))";

    const expected = [
      { id: "0_status_0", value: "true" },
      { id: "0_status_0", value: "false" },
    ];

    expect(deserializer(string)).toStrictEqual(expected);
  });

  test("should deserialize status filters (notIn)", () => {
    const string = "0(0*status*(status(notIn(true,false))))";

    const expected = [
      { id: "0_status_0", value: "TIMEOUT" },
      { id: "0_status_0", value: "OOM" },
      { id: "0_status_0", value: "false(reach)" },
    ];

    expect(deserializer(string)).toStrictEqual(expected);
  });

  test("should deserialize status filters in multiple runsets", () => {
    const string =
      "0(0*status*(status(in(true,false)))),1(0*status*(status(notIn(true,false))))";

    const expected = [
      { id: "0_status_0", value: "true" },
      { id: "0_status_0", value: "false" },
      { id: "1_status_0", value: "TIMEOUT" },
      { id: "1_status_0", value: "OOM" },
      { id: "1_status_0", value: "false(reach)" },
    ];

    expect(deserializer(string)).toStrictEqual(expected);
  });
  // categories

  test("should deserialize category filters (in)", () => {
    const string = "0(0*status*(category(in(correct,wrong))))";

    const expected = [
      { id: "0_status_0", value: "correct " },
      { id: "0_status_0", value: "wrong " },
    ];

    expect(deserializer(string)).toStrictEqual(expected);
  });

  test("should deserialize category filters (notIn)", () => {
    const string = "0(0*status*(category(notIn(correct,wrong))))";

    const expected = [
      { id: "0_status_0", value: "missing " },
      { id: "0_status_0", value: "unknown " },
    ];

    expect(deserializer(string)).toStrictEqual(expected);
  });

  test("should deserialize category filters in multiple runsets", () => {
    const string =
      "0(0*status*(category(in(correct,wrong)))),1(0*status*(category(notIn(correct,wrong))))";

    const expected = [
      { id: "0_status_0", value: "correct " },
      { id: "0_status_0", value: "wrong " },
      { id: "1_status_0", value: "missing " },
      { id: "1_status_0", value: "unknown " },
    ];

    expect(deserializer(string)).toStrictEqual(expected);
  });
});

describe("NumberFormatterBuilder", () => {
  let builder;
  beforeEach(() => {
    builder = new NumberFormatterBuilder(4);
  });
  test("should not count decimal point as significant number", () => {
    const formatter = builder.build();

    const number = "12.34";

    expect(formatter(number)).toBe("12.34");
  });

  test("should correctly format numbers with integral and fractional parts", () => {
    const formatter = builder.build();

    const number = "12.30000000123";

    expect(formatter(number)).toBe("12.30");
  });

  test("should handle if postfix has a decimal point", () => {
    const formatter = builder.build();

    const number = "1234.342";

    expect(formatter(number)).toBe("1234");
  });

  test("should handle if postfix has a leading decimal point", () => {
    const formatter = builder.build();

    const number = "12345.342";

    expect(formatter(number)).toBe("12350");
  });

  test("in fractions below 1, should add all zeros before the first non-zero digit", () => {
    const formatter = builder.build();

    const number = "0.000001234";

    expect(formatter(number)).toBe("0.000001234");
  });

  test("should identify comma and dots as decimal points", () => {
    const formatter = builder.build();

    const numberDot = "12.34";
    const numberComma = "12,34";

    expect(formatter(numberDot)).toBe("12.34");
    expect(formatter(numberComma)).toBe("12.34");
  });

  test("should round whole integer numbers after significant digits have been reached", () => {
    const formatter = builder.build();
    const number = "123456789";

    expect(formatter(number)).toBe("123500000");
  });

  test("should round fractions after significant digits have been reached", () => {
    const formatter = builder.build();
    const number = "0.123456789";

    expect(formatter(number)).toBe("0.1235");
  });

  test("should return number without rounding if no significant digits were provided", () => {
    const newBuilder = new NumberFormatterBuilder();
    const formatter = newBuilder.build();
    const number = "123456789";

    expect(formatter(number)).toBe("123456789");
  });

  test("should format whitespaces according to dataset context", () => {
    builder.addDataItem("1234");
    builder.addDataItem("0.12345");

    const formatter = builder.build();

    // we have 4 digits before and 5 digits after the decimal point
    const number1 = "23";
    const number2 = "23.1";
    const number3 = "0.123";
    const number4 = "0.01337";

    const expected1 = "  23      ";
    const expected2 = "  23.1    ";
    const expected3 = "    .123  ";
    const expected4 = "    .01337";

    const actual1 = formatter(number1, { whitespaceFormat: true });
    const actual2 = formatter(number2, { whitespaceFormat: true });
    const actual3 = formatter(number3, { whitespaceFormat: true });
    const actual4 = formatter(number4, { whitespaceFormat: true });

    expect(actual1).toBe(expected1);
    expect(actual2).toBe(expected2);
    expect(actual3).toBe(expected3);
    expect(actual4).toBe(expected4);
  });

  test("should format whitespaces with html", () => {
    builder.addDataItem("1234");
    builder.addDataItem("0.12345");

    const formatter = builder.build();

    // we have 4 digits before and 5 digits after the decimal point
    const number1 = "23";
    const number2 = "23.1";
    const number3 = "0.123";
    const number4 = "0.01337";

    const expected1 = "  23&#x2008;     ".replace(/ /g, "&#x2007;");
    const expected2 = "  23.1    ".replace(/ /g, "&#x2007;");
    const expected3 = "    .123  ".replace(/ /g, "&#x2007;");
    const expected4 = "    .01337".replace(/ /g, "&#x2007;");

    const actual1 = formatter(number1, { whitespaceFormat: true, html: true });
    const actual2 = formatter(number2, { whitespaceFormat: true, html: true });
    const actual3 = formatter(number3, { whitespaceFormat: true, html: true });
    const actual4 = formatter(number4, { whitespaceFormat: true, html: true });

    expect(actual1).toBe(expected1);
    expect(actual2).toBe(expected2);
    expect(actual3).toBe(expected3);
    expect(actual4).toBe(expected4);
  });
});

describe(
  "textSortMethod",
  () => {
    test("should evaluate order of objects with different values", () => {
      const smaller = { raw: "a" };
      const bigger = { raw: "b" };
      expect(textSortMethod(bigger, smaller)).toBeGreaterThan(0);
      expect(textSortMethod(smaller, bigger)).toBeLessThan(0);
    });

    test("should sort strings with different values without case sensitivy", () => {
      const smaller = { raw: "a" };
      const bigger = { raw: "B" };
      expect(textSortMethod(bigger, smaller)).toBeGreaterThan(0);
      expect(textSortMethod(smaller, bigger)).toBeLessThan(0);
    });

    test("should evaluate order of objects with same values", () => {
      const even1 = { raw: "a" };
      const even2 = { raw: "a" };
      expect(textSortMethod(even1, even2)).toBe(0);
    });

    test("should sort strings with same values without case sensitivity", () => {
      const even1 = { raw: "a" };
      const even2 = { raw: "A" };
      expect(textSortMethod(even1, even2)).toBe(0);
    });

    test("should sort empty value last", () => {
      const bigger = { raw: "" };
      const smaller = { raw: "a" };
      expect(textSortMethod(bigger, smaller)).toBeGreaterThan(0);
      expect(textSortMethod(smaller, bigger)).toBeLessThan(0);
    });

    test("should order items without raw prop last", () => {
      const testObject = { raw: "a" };
      const objectWithoutProp = { fake: "a" };
      expect(textSortMethod(objectWithoutProp, testObject)).toBeGreaterThan(0);
      expect(textSortMethod(testObject, objectWithoutProp)).toBeLessThan(0);
    });

    test("should be nil safe", () => {
      const testObject = { raw: "a" };
      expect(textSortMethod(null, testObject)).toBeGreaterThan(0);
      expect(textSortMethod(undefined, testObject)).toBeGreaterThan(0);
      expect(textSortMethod(testObject, null)).toBeLessThan(0);
      expect(textSortMethod(testObject, undefined)).toBeLessThan(0);
    });
  },

  describe("hasSameEntries", () => {
    test("should return true if the same arrays are passed", () => {
      const a = ["a", "b", "c"];
      const b = ["a", "b", "c"];
      expect(hasSameEntries(a, b)).toBe(true);
    });

    test("should return true if the same elements are present but in different order", () => {
      const a = ["a", "b", "c"];
      const b = ["c", "a", "b"];
      expect(hasSameEntries(a, b)).toBe(true);
    });

    test("should return true if the second array is a subset of the first one", () => {
      const a = ["a", "b", "c"];
      const b = ["a", "b"];
      expect(hasSameEntries(a, b)).toBe(true);
    });

    test("should return false if the second array has elements that are not in the first array", () => {
      const a = ["a", "b", "c"];
      const b = ["a", "b", "x"];
      expect(hasSameEntries(a, b)).toBe(false);
    });

    test("should return false if the first array is a subset of the second one", () => {
      const a = ["a", "b"];
      const b = ["a", "b", "c"];
      expect(hasSameEntries(a, b)).toBe(false);
    });

    test("should return false if the first array is empty", () => {
      const a = [];
      const b = ["a", "b", "c"];
      expect(hasSameEntries(a, b)).toBe(false);
    });

    test("should return true if the second array is empty", () => {
      const a = ["a", "b"];
      const b = [];
      expect(hasSameEntries(a, b)).toBe(true);
    });
  }),
);
